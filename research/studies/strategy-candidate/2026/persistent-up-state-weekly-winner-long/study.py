from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "liquid-perp-weekly-loser-continuation"
PARENT_MANIFEST = PARENT / "source_manifest.json"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"]
DATA_START = "2020-12-20T00:00:00Z"
DATA_END_EXCLUSIVE = "2025-07-01T00:00:00Z"
STAGES = {
    "development": ("2021-02-15T00:00:00Z", "2023-01-02T00:00:00Z"),
    "evaluation": ("2023-01-02T00:00:00Z", "2025-01-06T00:00:00Z"),
    "confirmation": ("2025-01-06T00:00:00Z", "2025-06-30T00:00:00Z"),
}
CONFIG = {
    "strategy_id": "RESEARCH_PERSISTENT_UP_STATE_WEEKLY_WINNER_LONG_0P25X_V1",
    "formation_days": 7,
    "hold_days": 7,
    "state_window_weeks": 4,
    "state_transition": "CURRENT_AND_PREVIOUS_COMPOUNDED_EQUAL_WEIGHT_MARKET_RETURN_GT_ZERO",
    "winner_count": 1,
    "winner_must_be_positive": True,
    "total_notional_fraction": 0.25,
    "annual_capital_hurdle": 0.04,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "long_funding_stress": {"positive_cost_multiplier": 1.5, "negative_benefit_multiplier": 0.5},
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def source_reuse_identity() -> dict[str, Any]:
    manifest = read_json(PARENT_MANIFEST)
    files = []
    total_bytes = 0
    for symbol in SYMBOLS:
        for family in ("kline_pages", "mark_pages", "funding_pages"):
            for item in manifest["symbols"][symbol][family]:
                files.append({
                    "symbol": symbol,
                    "family": family,
                    "path": item["path"],
                    "url": item["url"],
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                })
                total_bytes += int(item["bytes"])
    return {
        "source_study": str(PARENT),
        "source_manifest_path": str(PARENT_MANIFEST),
        "source_manifest_sha256": sha256_file(PARENT_MANIFEST),
        "source_manifest_content_digest": manifest["content_digest"],
        "files": len(files),
        "bytes": total_bytes,
        "items": files,
        "retrieval_rule": "Use each recorded Binance public REST URL and require the recorded SHA-256; no credentials.",
    }


def command_checkpoint(_args: argparse.Namespace) -> None:
    reuse = source_reuse_identity()
    reuse["created_at_utc"] = iso_now()
    reuse["content_digest"] = canonical_digest(reuse)
    write_json(HERE / "source_reuse_manifest.json", reuse)
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {"id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1", "instrument": "BTCUSDT-PERP"},
        "research_kind": "STRATEGY_CANDIDATE",
        "question": "Does a fixed weekly winner LONG only in consecutive positive four-week market states survive realistic costs, funding, beta baselines, robustness, and staged time evidence?",
        "evidence_boundary": "Exact rule outputs are unviewed, but all 2021-2025H1 underlying market paths were exposed by the reused parent study; no stage is truly untouched market evidence.",
        "symbols": SYMBOLS,
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "stages": STAGES,
        "config": CONFIG,
        "stage_open_rule": "development -> evaluation -> confirmation; open the next exact-rule output only after every prior gate passes",
        "support_limit": "Even all historical gates passing yields INSUFFICIENT_EVIDENCE until a genuinely new forward interval passes the frozen rule.",
        "allowed_fixes": "Only parsing, identity, deterministic-statistic, or implementation fixes that preserve the economic rule and are recorded before rerun.",
        "study_py_sha256": sha256_file(Path(__file__)),
        "preregistration_sha256": sha256_file(HERE / "preregistration.md"),
        "sources_sha256": sha256_file(HERE / "sources.md"),
        "source_reuse_manifest_sha256": sha256_file(HERE / "source_reuse_manifest.json"),
        "environment": {
            "python": platform.python_version(), "vectorbt": vbt.__version__, "pandas": pd.__version__,
            "numpy": np.__version__, "scipy": scipy.__version__,
        },
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"checkpoint": str(HERE / "checkpoint.json"), "digest": payload["content_digest"]}))


def ensure_checkpoint() -> dict[str, Any]:
    checkpoint = read_json(HERE / "checkpoint.json")
    if checkpoint["symbols"] != SYMBOLS or checkpoint["config"] != CONFIG:
        raise RuntimeError("checkpoint does not match fixed code configuration")
    if sha256_file(HERE / "source_reuse_manifest.json") != checkpoint["source_reuse_manifest_sha256"]:
        raise RuntimeError("source reuse identity changed after checkpoint")
    return checkpoint


def load_rows(items: list[dict[str, Any]]) -> list[Any]:
    rows: list[Any] = []
    for item in items:
        path = Path(item["path"])
        raw = path.read_bytes()
        if len(raw) != int(item["bytes"]) or sha256_bytes(raw) != item["sha256"]:
            raise RuntimeError(f"source identity mismatch: {path}")
        rows.extend(json.loads(raw))
    return rows


def load_symbol(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    source = read_json(PARENT_MANIFEST)["symbols"][symbol]
    bars = pd.DataFrame(load_rows(source["kline_pages"]), columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
        "trade_count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
    ])
    bars["open_time"] = pd.to_datetime(bars["open_time"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close", "volume", "quote_volume"):
        bars[column] = pd.to_numeric(bars[column], errors="raise")
    bars = bars.drop_duplicates("open_time", keep="last").sort_values("open_time").set_index("open_time")

    funding = pd.DataFrame(load_rows(source["funding_pages"]))
    funding["fundingTime"] = pd.to_datetime(funding["fundingTime"], unit="ms", utc=True)
    funding["fundingRate"] = pd.to_numeric(funding["fundingRate"], errors="raise")
    funding["markPrice"] = pd.to_numeric(funding["markPrice"], errors="coerce")
    funding = funding.drop_duplicates("fundingTime", keep="last").sort_values("fundingTime")

    marks = pd.DataFrame(load_rows(source["mark_pages"]), columns=[
        "open_time", "open", "high", "low", "close", "ignore_volume", "close_time",
        "ignore_quote", "ignore_count", "ignore_tb", "ignore_tq", "ignore",
    ])
    marks["close_time"] = pd.to_datetime(marks["close_time"], unit="ms", utc=True)
    marks["close"] = pd.to_numeric(marks["close"], errors="raise")
    marks = marks.drop_duplicates("close_time", keep="last").sort_values("close_time")
    matched = pd.merge_asof(
        funding, marks[["close_time", "close"]], left_on="fundingTime", right_on="close_time",
        direction="nearest", tolerance=pd.Timedelta(minutes=1),
    )
    funding["mark_price_from_response"] = funding["markPrice"].notna()
    funding["mark_match_delta_ms"] = (matched["close_time"] - matched["fundingTime"]).dt.total_seconds() * 1000.0
    funding["markPrice"] = funding["markPrice"].fillna(matched["close"])
    return bars, funding.set_index("fundingTime").sort_index()


def load_all() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    bars: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        bars[symbol], funding[symbol] = load_symbol(symbol)
    return bars, funding


def command_inspect(_args: argparse.Namespace) -> None:
    ensure_checkpoint()
    reuse = read_json(HERE / "source_reuse_manifest.json")
    for item in reuse["items"]:
        path = Path(item["path"])
        raw = path.read_bytes()
        if len(raw) != int(item["bytes"]) or sha256_bytes(raw) != item["sha256"]:
            raise RuntimeError(f"reuse file failed identity check: {path}")
    bars, funding = load_all()
    expected = pd.date_range(pd.Timestamp(DATA_START), pd.Timestamp(DATA_END_EXCLUSIVE), freq="1D", inclusive="left")
    payload: dict[str, Any] = {"checked_at_utc": iso_now(), "status": "PASS", "symbols": {}}
    for symbol in SYMBOLS:
        frame = bars[symbol][(bars[symbol].index >= expected[0]) & (bars[symbol].index < pd.Timestamp(DATA_END_EXCLUSIVE))]
        rates = funding[symbol][(funding[symbol].index >= expected[0]) & (funding[symbol].index < pd.Timestamp(DATA_END_EXCLUSIVE))]
        missing = expected.difference(frame.index)
        invalid = int(((frame[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
        invalid_range = int(((frame["high"] < frame[["open", "close"]].max(axis=1)) | (frame["low"] > frame[["open", "close"]].min(axis=1))).sum())
        missing_mark = int(rates["markPrice"].isna().sum())
        status = "PASS" if len(missing) == 0 and invalid == 0 and invalid_range == 0 and len(rates) > 4900 and missing_mark == 0 else "FAIL"
        if status != "PASS":
            payload["status"] = "FAIL"
        payload["symbols"][symbol] = {
            "status": status, "bars": int(len(frame)), "missing_bars": int(len(missing)),
            "invalid_ohlc": invalid, "invalid_range": invalid_range, "funding_rows": int(len(rates)),
            "missing_mark_price": missing_mark,
            "mark_from_funding_response": int(rates["mark_price_from_response"].sum()),
            "mark_from_official_8h_kline": int((~rates["mark_price_from_response"]).sum()),
            "maximum_mark_match_delta_ms": float(rates["mark_match_delta_ms"].abs().max()),
            "median_daily_quote_volume": float(frame["quote_volume"].median()),
        }
    payload["source_reuse_manifest_sha256"] = sha256_file(HERE / "source_reuse_manifest.json")
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / "data_quality.json", payload)
    print(json.dumps({"status": payload["status"], "symbols": len(SYMBOLS), "files": reuse["files"]}))
    if payload["status"] != "PASS":
        raise RuntimeError("data quality failed")


def market_week_return(bars: dict[str, pd.DataFrame], decision: pd.Timestamp, formation_days: int = 7) -> float:
    earlier = decision - pd.Timedelta(days=formation_days)
    values = [float(bars[s].at[decision, "close"] / bars[s].at[earlier, "close"] - 1.0) for s in SYMBOLS]
    return float(np.mean(values))


def market_state(bars: dict[str, pd.DataFrame], decision: pd.Timestamp, window_weeks: int) -> tuple[float, float, bool, bool]:
    weekly = [market_week_return(bars, decision - pd.Timedelta(days=7 * lag)) for lag in range(window_weeks + 1)]
    current = float(np.prod(1.0 + np.asarray(weekly[:window_weeks])) - 1.0)
    previous = float(np.prod(1.0 + np.asarray(weekly[1:])) - 1.0)
    return current, previous, current > 0.0, previous > 0.0


def stressed_long_rate(rate: float) -> float:
    if rate > 0:
        return rate * float(CONFIG["long_funding_stress"]["positive_cost_multiplier"])
    return rate * float(CONFIG["long_funding_stress"]["negative_benefit_multiplier"])


def build_trades(
    bars: dict[str, pd.DataFrame], funding: dict[str, pd.DataFrame], stage: str, *,
    formation_days: int = 7, state_window_weeks: int = 4, state_mode: str = "up_up", selection_mode: str = "winner",
) -> pd.DataFrame:
    start, end = map(pd.Timestamp, STAGES[stage])
    rows: list[dict[str, Any]] = []
    for entry in pd.date_range(start, end, freq="7D", inclusive="left"):
        exit_time = entry + pd.Timedelta(days=7)
        decision = entry - pd.Timedelta(days=1)
        earlier = decision - pd.Timedelta(days=formation_days)
        for symbol in SYMBOLS:
            for needed in (decision, earlier, entry, exit_time):
                if needed not in bars[symbol].index:
                    raise RuntimeError(f"incomplete weekly input: {symbol} {needed}")
        current_state, previous_state, current_up, previous_up = market_state(bars, decision, state_window_weeks)
        eligible = state_mode == "none" or (state_mode == "up" and current_up) or (state_mode == "up_up" and current_up and previous_up)
        formation = {s: float(bars[s].at[decision, "close"] / bars[s].at[earlier, "close"] - 1.0) for s in SYMBOLS}
        ranked = sorted(SYMBOLS, key=lambda s: (-formation[s], s))
        if selection_mode == "winner":
            selected = ranked[:1] if formation[ranked[0]] > 0 else []
        elif selection_mode == "all":
            selected = SYMBOLS
        elif selection_mode == "btc":
            selected = ["BTCUSDT"]
        else:
            raise ValueError(selection_mode)
        if not eligible or not selected:
            continue
        leg_weight = float(CONFIG["total_notional_fraction"]) / len(selected)
        for symbol in selected:
            entry_price = float(bars[symbol].at[entry, "open"])
            exit_price = float(bars[symbol].at[exit_time, "open"])
            quantity = leg_weight / entry_price
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index <= exit_time)]
            actual_funding = -float((quantity * rates["markPrice"] * rates["fundingRate"]).sum())
            stress_funding = -float((quantity * rates["markPrice"] * rates["fundingRate"].map(stressed_long_rate)).sum())
            rows.append({
                "trade_id": f"{stage}-{entry:%Y%m%d}-{symbol}-{formation_days}-{state_window_weeks}-{state_mode}-{selection_mode}",
                "week_id": f"{stage}-{entry:%Y%m%d}", "entry_time": entry, "exit_time": exit_time,
                "decision_time": decision, "symbol": symbol, "formation_days": formation_days,
                "state_window_weeks": state_window_weeks, "state_mode": state_mode, "selection_mode": selection_mode,
                "current_state_return": current_state, "previous_state_return": previous_state,
                "formation_return": formation[symbol], "market_formation_return": float(np.mean(list(formation.values()))),
                "leg_weight": leg_weight, "entry_price": entry_price, "exit_price": exit_price,
                "quantity_per_unit_plan_capital": quantity, "funding_events": int(len(rates)),
                "actual_funding_return": actual_funding, "stress_funding_return": stress_funding,
                "gross_long_return": leg_weight * (exit_price / entry_price - 1.0),
            })
    return pd.DataFrame(rows)


def vectorbt_long_returns(trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    columns = trades["trade_id"].tolist()
    prices = pd.DataFrame([trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)], columns=columns)
    quantity = trades["quantity_per_unit_plan_capital"].to_numpy(float)
    sizes = pd.DataFrame([quantity, -quantity], columns=columns)
    portfolio = vbt.Portfolio.from_orders(
        prices, size=sizes, size_type="amount", direction="both", fees=fee, slippage=slippage,
        init_cash=1.0, freq="1D",
    )
    return portfolio.total_return().reindex(columns).to_numpy(float)


def manual_long_return(row: pd.Series, fee: float, slippage: float) -> float:
    quantity = float(row["quantity_per_unit_plan_capital"])
    entry_execution = float(row["entry_price"]) * (1.0 + slippage)
    exit_execution = float(row["exit_price"]) * (1.0 - slippage)
    return quantity * (exit_execution - entry_execution) - quantity * entry_execution * fee - quantity * exit_execution * fee


def attach_returns(trades: pd.DataFrame) -> pd.DataFrame:
    output = trades.copy()
    for scenario, assumptions in CONFIG["costs"].items():
        vbt_return = vectorbt_long_returns(output, float(assumptions["fee_per_side"]), float(assumptions["slippage_per_side"]))
        manual = output.apply(
            manual_long_return, axis=1, fee=float(assumptions["fee_per_side"]), slippage=float(assumptions["slippage_per_side"]),
        ).to_numpy(float)
        output[f"{scenario}_price_cost_return"] = vbt_return
        output[f"{scenario}_reconciliation_error"] = vbt_return - manual
        funding_column = "stress_funding_return" if assumptions["funding_stress"] else "actual_funding_return"
        output[f"{scenario}_net_return"] = vbt_return + output[funding_column].to_numpy(float)
    return output


def weekly_returns(trades: pd.DataFrame, column: str) -> pd.Series:
    return trades.groupby("entry_time")[column].sum().sort_index()


def block_bootstrap_mean_ci(values: np.ndarray) -> list[float]:
    values = np.asarray(values, dtype=float)
    block = int(CONFIG["bootstrap"]["block_weeks"])
    reps = int(CONFIG["bootstrap"]["repetitions"])
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"]))
    means = np.empty(reps)
    for index in range(reps):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(block)) % len(values)).tolist())
        means[index] = values[np.asarray(chosen[:len(values)])].mean()
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def daily_equity(trades: pd.DataFrame, bars: dict[str, pd.DataFrame], funding: dict[str, pd.DataFrame], scenario: str) -> pd.Series:
    assumptions = CONFIG["costs"][scenario]
    fee = float(assumptions["fee_per_side"])
    slippage = float(assumptions["slippage_per_side"])
    capital = 1.0
    points: dict[pd.Timestamp, float] = {}
    for entry, legs in trades.groupby("entry_time", sort=True):
        exit_time = pd.Timestamp(legs["exit_time"].iloc[0])
        normalized_by_day: dict[pd.Timestamp, float] = {}
        for _, row in legs.iterrows():
            symbol = str(row["symbol"])
            quantity = float(row["quantity_per_unit_plan_capital"])
            entry_execution = float(row["entry_price"]) * (1.0 + slippage)
            entry_fee = quantity * entry_execution * fee
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index <= exit_time)].copy()
            if assumptions["funding_stress"]:
                rates["fundingRate"] = rates["fundingRate"].map(stressed_long_rate)
            for day, bar in bars[symbol][(bars[symbol].index >= entry) & (bars[symbol].index < exit_time)].iterrows():
                settled = rates[rates.index < day + pd.Timedelta(days=1)]
                funding_cashflow = -float((quantity * settled["markPrice"] * settled["fundingRate"]).sum())
                leg_change = quantity * (float(bar["close"]) - entry_execution) - entry_fee + funding_cashflow
                normalized_by_day[day] = normalized_by_day.get(day, 1.0) + leg_change
        for day, normalized in normalized_by_day.items():
            points[day] = capital * normalized
        capital *= 1.0 + float(legs[f"{scenario}_net_return"].sum())
        points[exit_time] = capital
    return pd.Series(points, dtype="float64").sort_index()


def hurdle_adjust(total: float, start: pd.Timestamp, end: pd.Timestamp) -> float:
    years = (end - start).days / 365.0
    return (1.0 + total) / ((1.0 + float(CONFIG["annual_capital_hurdle"])) ** years) - 1.0


def summarize(trades: pd.DataFrame, bars: dict[str, pd.DataFrame], funding: dict[str, pd.DataFrame], stage: str) -> dict[str, Any]:
    start, end = map(pd.Timestamp, STAGES[stage])
    result: dict[str, Any] = {
        "eligible_weeks": int(trades["entry_time"].nunique()), "legs": int(len(trades)),
        "funding_events": int(trades["funding_events"].sum()),
        "selection_counts": {k: int(v) for k, v in trades["symbol"].value_counts().reindex(SYMBOLS, fill_value=0).items()},
        "maximum_vectorbt_reconciliation_error": float(max(trades[f"{s}_reconciliation_error"].abs().max() for s in CONFIG["costs"])),
        "by_year": {}, "by_symbol": {}, "scenarios": {},
    }
    for scenario in CONFIG["costs"]:
        weekly = weekly_returns(trades, f"{scenario}_net_return")
        total = float(np.prod(1.0 + weekly.to_numpy(float)) - 1.0)
        equity = daily_equity(trades, bars, funding, scenario)
        running_max = equity.cummax().clip(lower=1.0)
        result["scenarios"][scenario] = {
            "total_return": total,
            "annualized_return": float((1.0 + total) ** (365.0 / (end - start).days) - 1.0),
            "daily_max_drawdown": float((equity / running_max - 1.0).min()),
            "weekly_mean": float(weekly.mean()),
            "weekly_mean_bootstrap_95pct": block_bootstrap_mean_ci(weekly.to_numpy(float)),
            "return_after_4pct_annual_hurdle": hurdle_adjust(total, start, end),
        }
    base = weekly_returns(trades, "base_net_return")
    for year in sorted(set(base.index.year.tolist())):
        values = base[base.index.year == year]
        result["by_year"][str(year)] = {
            "weeks": int(len(values)),
            "return": float(np.prod(1.0 + values.to_numpy(float)) - 1.0),
        }
    symbol_pnl = trades.groupby("symbol")["base_net_return"].sum().reindex(SYMBOLS, fill_value=0.0)
    positive = float(symbol_pnl.clip(lower=0.0).sum())
    result["by_symbol"] = {k: float(v) for k, v in symbol_pnl.items()}
    result["largest_positive_pnl_share"] = float(symbol_pnl.clip(lower=0.0).max() / positive) if positive > 0 else 1.0
    return result


def comparison(main: pd.DataFrame, baseline: pd.DataFrame, main_column: str, baseline_column: str) -> dict[str, Any]:
    left = weekly_returns(main, main_column)
    right = weekly_returns(baseline, baseline_column).reindex(left.index)
    if right.isna().any():
        raise RuntimeError("baseline does not cover every main eligible week")
    diff = left - right
    return {
        "mean": float(diff.mean()), "arithmetic_total": float(diff.sum()),
        "bootstrap_95pct": block_bootstrap_mean_ci(diff.to_numpy(float)),
        "positive_weeks_fraction": float((diff > 0).mean()),
    }


def stage_authorized(stage: str) -> None:
    prior = {"evaluation": "development", "confirmation": "evaluation"}.get(stage)
    if prior and read_json(HERE / f"{prior}_gate.json")["status"] != "PASS":
        raise RuntimeError(f"{stage} not authorized by sequential gate")


def command_analyze(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    stage_authorized(args.stage)
    if read_json(HERE / "data_quality.json")["status"] != "PASS":
        raise RuntimeError("data quality is not PASS")
    bars, funding = load_all()
    configs = {
        "main": dict(formation_days=7, state_window_weeks=4, state_mode="up_up", selection_mode="winner"),
        "state_market": dict(formation_days=7, state_window_weeks=4, state_mode="up_up", selection_mode="all"),
        "state_btc": dict(formation_days=7, state_window_weeks=4, state_mode="up_up", selection_mode="btc"),
        "unconditional_winner": dict(formation_days=7, state_window_weeks=4, state_mode="none", selection_mode="winner"),
        "up_only_winner": dict(formation_days=7, state_window_weeks=4, state_mode="up", selection_mode="winner"),
        "formation14": dict(formation_days=14, state_window_weeks=4, state_mode="up_up", selection_mode="winner"),
        "state3": dict(formation_days=7, state_window_weeks=3, state_mode="up_up", selection_mode="winner"),
        "state6": dict(formation_days=7, state_window_weeks=6, state_mode="up_up", selection_mode="winner"),
    }
    trades = {name: attach_returns(build_trades(bars, funding, args.stage, **cfg)) for name, cfg in configs.items()}
    for name, frame in trades.items():
        frame.to_csv(HERE / f"{args.stage}_{name}_trades.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    summaries = {name: summarize(frame, bars, funding, args.stage) for name, frame in trades.items()}
    payload = {
        "generated_at_utc": iso_now(), "stage": args.stage,
        "period": {"start": STAGES[args.stage][0], "end_exclusive": STAGES[args.stage][1]},
        "main": summaries["main"],
        "diagnostics": {name: value for name, value in summaries.items() if name != "main"},
        "comparisons": {
            "gross_excess_vs_state_market": comparison(trades["main"], trades["state_market"], "gross_long_return", "gross_long_return"),
            "base_excess_vs_state_market": comparison(trades["main"], trades["state_market"], "base_net_return", "base_net_return"),
            "base_excess_vs_state_btc": comparison(trades["main"], trades["state_btc"], "base_net_return", "base_net_return"),
        },
        "search_disclosure": {"selectable_primary_configurations": 1, "nonselectable_diagnostic_configurations": 7},
        "trade_csv_sha256": {name: sha256_file(HERE / f"{args.stage}_{name}_trades.csv") for name in trades},
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / f"{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage, "eligible_weeks": payload["main"]["eligible_weeks"],
        "base_total": payload["main"]["scenarios"]["base"]["total_return"],
        "stress_total": payload["main"]["scenarios"]["stress"]["total_return"],
        "gross_excess_mean": payload["comparisons"]["gross_excess_vs_state_market"]["mean"],
    }))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    main = result["main"]
    scenarios = main["scenarios"]
    neighbors = [result["diagnostics"][name]["scenarios"]["stress"]["total_return"] for name in ("formation14", "state3", "state6")]
    checks = {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "vectorbt_reconciled": main["maximum_vectorbt_reconciliation_error"] <= 1e-10,
        "base_total_positive": scenarios["base"]["total_return"] > 0,
        "stress_total_positive": scenarios["stress"]["total_return"] > 0,
        "stress_after_hurdle_positive": scenarios["stress"]["return_after_4pct_annual_hurdle"] > 0,
        "gross_excess_vs_state_market_positive": result["comparisons"]["gross_excess_vs_state_market"]["mean"] > 0,
        "base_beats_state_market": scenarios["base"]["total_return"] > result["diagnostics"]["state_market"]["scenarios"]["base"]["total_return"],
        "base_beats_state_btc": scenarios["base"]["total_return"] > result["diagnostics"]["state_btc"]["scenarios"]["base"]["total_return"],
        "at_least_two_of_three_neighbors_stress_nonnegative": sum(value >= 0 for value in neighbors) >= 2,
    }
    if stage == "confirmation":
        checks.update({
            "eligible_weeks_at_least_8": main["eligible_weeks"] >= 8,
            "daily_drawdown_above_minus_10pct": scenarios["base"]["daily_max_drawdown"] > -0.10,
        })
    else:
        checks.update({
            "eligible_weeks_at_least_30": main["eligible_weeks"] >= 30,
            "each_full_year_at_least_8_weeks": all(item["weeks"] >= 8 for item in main["by_year"].values()),
            "each_full_year_base_positive": all(item["return"] > 0 for item in main["by_year"].values()),
            "stress_weekly_bootstrap_lower_positive": scenarios["stress"]["weekly_mean_bootstrap_95pct"][0] > 0,
            "gross_excess_bootstrap_lower_positive": result["comparisons"]["gross_excess_vs_state_market"]["bootstrap_95pct"][0] > 0,
            "daily_drawdown_above_minus_15pct": scenarios["base"]["daily_max_drawdown"] > -0.15,
            "four_symbols_selected_at_least_twice": sum(value >= 2 for value in main["selection_counts"].values()) >= 4,
            "largest_positive_pnl_share_at_most_half": main["largest_positive_pnl_share"] <= 0.50,
        })
    return checks


def command_gate(args: argparse.Namespace) -> None:
    result = read_json(HERE / f"{args.stage}.json")
    checks = gate_checks(args.stage, result)
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "generated_at_utc": iso_now(), "stage": args.stage, "status": status, "checks": checks,
        "failed_checks": [key for key, value in checks.items() if not value], "result_digest": result["content_digest"],
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / f"{args.stage}_gate.json", payload)
    if status == "FAIL":
        economic_positive = result["main"]["scenarios"]["base"]["total_return"] > 0 and result["main"]["scenarios"]["stress"]["total_return"] > 0
        stopped = {
            "generated_at_utc": iso_now(),
            "conclusion": "INSUFFICIENT_EVIDENCE" if economic_positive else "DOES_NOT_SUPPORT",
            "stopped_after": args.stage, "gate_status": status, "failed_checks": payload["failed_checks"],
            "main": result["main"], "comparisons": result["comparisons"], "diagnostics": result["diagnostics"],
            "later_stages": "NOT_OPENED_BY_SEQUENTIAL_GATE", "handoff": "NOT_GENERATED", "product_effects": "NONE",
        }
        stopped["content_digest"] = canonical_digest(stopped)
        write_json(HERE / "results.json", stopped)
    print(json.dumps({"stage": args.stage, "status": status, "failed": payload["failed_checks"]}))


def command_conclude(_args: argparse.Namespace) -> None:
    stages = {stage: read_json(HERE / f"{stage}.json") for stage in STAGES}
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in STAGES}
    if not all(gate["status"] == "PASS" for gate in gates.values()):
        raise RuntimeError("conclude requires all historical gates PASS")
    payload = {
        "generated_at_utc": iso_now(), "conclusion": "INSUFFICIENT_EVIDENCE",
        "stage_gates": {stage: gate["status"] for stage, gate in gates.items()},
        "stage_main": {stage: result["main"] for stage, result in stages.items()},
        "reason": "All underlying market paths were exposed before this question; a genuinely new forward interval is required.",
        "forward_requirement": "Frozen rule; at least 26 eligible weeks spanning two market states, then identical cost, baseline, robustness, and risk gates.",
        "handoff": "NOT_GENERATED", "product_effects": "NONE",
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / "results.json", payload)
    print(json.dumps({"conclusion": payload["conclusion"]}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persistent UP-state weekly winner LONG")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("inspect").set_defaults(func=command_inspect)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--stage", choices=tuple(STAGES), required=True)
    analyze.set_defaults(func=command_analyze)
    gate = sub.add_parser("gate")
    gate.add_argument("--stage", choices=tuple(STAGES), required=True)
    gate.set_defaults(func=command_gate)
    sub.add_parser("conclude").set_defaults(func=command_conclude)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
