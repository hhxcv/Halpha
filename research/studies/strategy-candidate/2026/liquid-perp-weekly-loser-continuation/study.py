from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
CACHE_ROOT = Path(os.environ.get(
    "HALPHA_WEEKLY_LOSER_CACHE",
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "liquid-perp-weekly-loser-continuation/2026-07-22-v1",
))
BASE_URL = "https://fapi.binance.com"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"]
DATA_START = "2020-12-20T00:00:00Z"
DATA_END_EXCLUSIVE = "2025-07-01T00:00:00Z"
STAGES = {
    "development": ("2021-01-04T00:00:00Z", "2023-01-02T00:00:00Z"),
    "evaluation": ("2023-01-02T00:00:00Z", "2025-01-06T00:00:00Z"),
    "confirmation": ("2025-01-06T00:00:00Z", "2025-06-30T00:00:00Z"),
}
CONFIG = {
    "strategy_id": "RESEARCH_LIQUID_PERP_WEEKLY_BOTTOM1_SHORT_7D_0P25X_V1",
    "formation_days": 7,
    "hold_days": 7,
    "bottom_count": 1,
    "total_notional_fraction": 0.25,
    "annual_capital_hurdle": 0.04,
    "diagnostics": {
        "formation_14d": {"formation_days": 14, "bottom_count": 1},
        "bottom_2": {"formation_days": 7, "bottom_count": 2},
        "equal_weight_short": {"formation_days": 7, "bottom_count": 6},
        "btc_short": {"symbols": ["BTCUSDT"]},
    },
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "short_funding_stress": {"positive_benefit_multiplier": 0.5, "negative_cost_multiplier": 1.5},
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1000)


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def request_json(endpoint: str, params: dict[str, Any] | None = None) -> tuple[bytes, str]:
    query = urllib.parse.urlencode(params or {})
    url = f"{BASE_URL}{endpoint}" + (f"?{query}" if query else "")
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Halpha-Research/1.0"})
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
            json.loads(raw)
            return raw, url
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def command_checkpoint(_args: argparse.Namespace) -> None:
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {"id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1"},
        "research_kind": "STRATEGY_CANDIDATE",
        "question": "Does weekly bottom-1 continuation in six liquid Binance USD-M perps survive funding, costs, market-beta control, and sequential holdouts?",
        "evidence_boundary": "Other rules and frequencies on these assets are exposed; this exact weekly cross-sectional ranking and stage output are unviewed.",
        "symbols": SYMBOLS,
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "stages": STAGES,
        "config": CONFIG,
        "stage_open_rule": "development -> evaluation -> confirmation; next stage only after every prior gate passes",
        "allowed_fixes": "retrieval, parsing, completeness, deterministic statistics, or implementation bugs that do not change the economic rule; record every outcome-affecting fix",
        "study_py_sha256": sha256_file(Path(__file__)),
        "preregistration_sha256": sha256_file(HERE / "preregistration.md"),
        "sources_sha256": sha256_file(HERE / "sources.md"),
        "environment": {
            "python": platform.python_version(), "vectorbt": vbt.__version__,
            "pandas": pd.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
        },
        "cache_root": str(CACHE_ROOT),
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"checkpoint": str(HERE / "checkpoint.json"), "digest": payload["content_digest"]}))


def ensure_checkpoint() -> dict[str, Any]:
    checkpoint = read_json(HERE / "checkpoint.json")
    if checkpoint["symbols"] != SYMBOLS or checkpoint["config"] != CONFIG:
        raise RuntimeError("checkpoint does not match fixed configuration")
    return checkpoint


def fetch_pages(
    endpoint: str,
    base_params: dict[str, Any],
    time_key: str,
    limit: int,
    out_dir: Path,
    start_value: str = DATA_START,
) -> list[dict[str, Any]]:
    cursor = utc_ms(start_value)
    end = utc_ms(DATA_END_EXCLUSIVE)
    pages: list[dict[str, Any]] = []
    page_number = 0
    while cursor < end:
        params = dict(base_params)
        params.update({"startTime": cursor, "endTime": end - 1, "limit": limit})
        raw, url = request_json(endpoint, params)
        rows = json.loads(raw)
        if not rows:
            break
        path = out_dir / f"{time_key}-{page_number:03d}.json"
        if path.exists() and path.read_bytes() != raw:
            raise RuntimeError(f"refusing to overwrite different raw page: {path}")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        first = int(rows[0][0] if isinstance(rows[0], list) else rows[0][time_key])
        last = int(rows[-1][0] if isinstance(rows[-1], list) else rows[-1][time_key])
        pages.append({
            "url": url, "path": str(path), "bytes": len(raw), "sha256": sha256_bytes(raw),
            "rows": len(rows), "first_time_ms": first, "last_time_ms": last,
        })
        if last + 1 <= cursor:
            raise RuntimeError(f"non-advancing pagination: {endpoint}")
        cursor = last + 1
        page_number += 1
        time.sleep(0.08)
    return pages


def command_fetch(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    manifest: dict[str, Any] = {
        "accessed_at_utc": iso_now(), "checkpoint_digest": checkpoint["content_digest"],
        "source": "Binance public USD-M REST; no credentials", "symbols": {},
    }
    for symbol in SYMBOLS:
        root = CACHE_ROOT / symbol / "raw"
        manifest["symbols"][symbol] = {
            "kline_pages": fetch_pages("/fapi/v1/klines", {"symbol": symbol, "interval": "1d"}, "openTime", 1500, root / "klines"),
            "mark_pages": fetch_pages(
                "/fapi/v1/markPriceKlines", {"symbol": symbol, "interval": "8h"}, "openTime", 1500,
                root / "mark-price-klines", start_value="2020-12-19T16:00:00Z",
            ),
            "funding_pages": fetch_pages("/fapi/v1/fundingRate", {"symbol": symbol}, "fundingTime", 1000, root / "funding"),
        }
        print(json.dumps({"fetched": symbol}))
    manifest["content_digest"] = canonical_digest(manifest)
    write_json(HERE / "source_manifest.json", manifest)
    print(json.dumps({"manifest": str(HERE / "source_manifest.json"), "digest": manifest["content_digest"]}))


def load_rows(items: list[dict[str, Any]]) -> list[Any]:
    rows: list[Any] = []
    for item in items:
        raw = Path(item["path"]).read_bytes()
        if len(raw) != item["bytes"] or sha256_bytes(raw) != item["sha256"]:
            raise RuntimeError(f"source identity mismatch: {item['path']}")
        rows.extend(json.loads(raw))
    return rows


def load_symbol(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    item = read_json(HERE / "source_manifest.json")["symbols"][symbol]
    bars = pd.DataFrame(load_rows(item["kline_pages"]), columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
        "trade_count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
    ])
    bars["open_time"] = pd.to_datetime(bars["open_time"], unit="ms", utc=True)
    for column in ["open", "high", "low", "close", "volume", "quote_volume"]:
        bars[column] = pd.to_numeric(bars[column], errors="raise")
    bars = bars.drop_duplicates("open_time", keep="last").sort_values("open_time").set_index("open_time")

    funding = pd.DataFrame(load_rows(item["funding_pages"]))
    funding["fundingTime"] = pd.to_datetime(funding["fundingTime"], unit="ms", utc=True)
    funding["fundingRate"] = pd.to_numeric(funding["fundingRate"], errors="raise")
    funding["markPrice"] = pd.to_numeric(funding["markPrice"], errors="coerce")
    funding = funding.drop_duplicates("fundingTime", keep="last").sort_values("fundingTime")

    marks = pd.DataFrame(load_rows(item["mark_pages"]), columns=[
        "open_time", "open", "high", "low", "close", "ignore_volume", "close_time",
        "ignore_quote", "ignore_count", "ignore_tb", "ignore_tq", "ignore",
    ])
    marks["close_time"] = pd.to_datetime(marks["close_time"], unit="ms", utc=True)
    marks["close"] = pd.to_numeric(marks["close"], errors="raise")
    marks = marks.drop_duplicates("close_time", keep="last").sort_values("close_time")
    matched = pd.merge_asof(
        funding.sort_values("fundingTime"), marks[["close_time", "close"]],
        left_on="fundingTime", right_on="close_time", direction="nearest", tolerance=pd.Timedelta(minutes=1),
    )
    funding["mark_price_from_funding_response"] = funding["markPrice"].notna()
    funding["mark_match_delta_ms"] = (matched["close_time"] - matched["fundingTime"]).dt.total_seconds() * 1000.0
    funding["markPrice"] = funding["markPrice"].fillna(matched["close"])
    funding = funding.set_index("fundingTime").sort_index()
    return bars, funding


def load_all() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    bars: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        bars[symbol], funding[symbol] = load_symbol(symbol)
    return bars, funding


def command_inspect(_args: argparse.Namespace) -> None:
    ensure_checkpoint()
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
            "invalid_ohlc": invalid, "invalid_range": invalid_range,
            "funding_rows": int(len(rates)), "missing_mark_price": missing_mark,
            "mark_from_funding_response": int(rates["mark_price_from_funding_response"].sum()),
            "mark_from_official_8h_kline": int((~rates["mark_price_from_funding_response"]).sum()),
            "maximum_mark_match_delta_ms": float(rates["mark_match_delta_ms"].abs().max()),
            "median_daily_quote_volume": float(frame["quote_volume"].median()),
            "minimum_30d_median_quote_volume": float(frame["quote_volume"].rolling(30).median().dropna().min()),
        }
    payload["source_manifest_sha256"] = sha256_file(HERE / "source_manifest.json")
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / "data_quality.json", payload)
    print(json.dumps({"status": payload["status"], "symbols": len(SYMBOLS)}))
    if payload["status"] != "PASS":
        raise RuntimeError("data quality failed")


def stressed_short_rate(rate: float) -> float:
    if rate > 0:
        return rate * CONFIG["short_funding_stress"]["positive_benefit_multiplier"]
    return rate * CONFIG["short_funding_stress"]["negative_cost_multiplier"]


def build_trades(
    bars: dict[str, pd.DataFrame], funding: dict[str, pd.DataFrame], stage: str,
    formation_days: int, bottom_count: int, fixed_symbols: list[str] | None = None,
) -> pd.DataFrame:
    start, end = map(pd.Timestamp, STAGES[stage])
    entries = pd.date_range(start, end, freq="7D", inclusive="left")
    rows: list[dict[str, Any]] = []
    for entry in entries:
        exit_time = entry + pd.Timedelta(days=7)
        decision = entry - pd.Timedelta(days=1)
        earlier = decision - pd.Timedelta(days=formation_days)
        universe = fixed_symbols or SYMBOLS
        formation = {}
        for symbol in universe:
            if decision not in bars[symbol].index or earlier not in bars[symbol].index or entry not in bars[symbol].index or exit_time not in bars[symbol].index:
                raise RuntimeError(f"incomplete weekly input: {symbol} {entry}")
            formation[symbol] = float(bars[symbol].at[decision, "close"] / bars[symbol].at[earlier, "close"] - 1.0)
        selected = sorted(universe, key=lambda symbol: (formation[symbol], symbol))[:bottom_count]
        leg_weight = float(CONFIG["total_notional_fraction"]) / len(selected)
        market_formation = float(np.mean(list(formation.values())))
        for symbol in selected:
            entry_price = float(bars[symbol].at[entry, "open"])
            exit_price = float(bars[symbol].at[exit_time, "open"])
            quantity = leg_weight / entry_price
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index <= exit_time)]
            actual_funding = float((quantity * rates["markPrice"] * rates["fundingRate"]).sum())
            stress_funding = float((quantity * rates["markPrice"] * rates["fundingRate"].map(stressed_short_rate)).sum())
            rows.append({
                "trade_id": f"{stage}-{entry.strftime('%Y%m%d')}-{symbol}-{formation_days}-{bottom_count}",
                "week_id": f"{stage}-{entry.strftime('%Y%m%d')}", "entry_time": entry, "exit_time": exit_time,
                "decision_time": decision, "symbol": symbol, "formation_days": formation_days,
                "formation_return": formation[symbol], "market_formation_return": market_formation,
                "formation_gap": formation[symbol] - market_formation, "leg_weight": leg_weight,
                "entry_price": entry_price, "exit_price": exit_price,
                "quantity_per_unit_plan_capital": quantity, "funding_events": int(len(rates)),
                "actual_funding_return": actual_funding, "stress_funding_return": stress_funding,
                "gross_short_return": leg_weight * (1.0 - exit_price / entry_price),
            })
    return pd.DataFrame(rows)


def vectorbt_short_returns(trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    columns = trades["trade_id"].tolist()
    prices = pd.DataFrame(
        [trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)],
        index=pd.Index([0, 1], name="step"), columns=columns,
    )
    quantity = trades["quantity_per_unit_plan_capital"].to_numpy(float)
    sizes = pd.DataFrame([-quantity, quantity], index=prices.index, columns=columns)
    portfolio = vbt.Portfolio.from_orders(
        prices, size=sizes, size_type="amount", direction="both", fees=fee, slippage=slippage,
        init_cash=1.0, freq="1D",
    )
    return portfolio.total_return().reindex(columns).to_numpy(float)


def manual_short_return(row: pd.Series, fee: float, slippage: float) -> float:
    quantity = float(row["quantity_per_unit_plan_capital"])
    entry_execution = float(row["entry_price"]) * (1.0 - slippage)
    exit_execution = float(row["exit_price"]) * (1.0 + slippage)
    return quantity * (entry_execution - exit_execution) - quantity * entry_execution * fee - quantity * exit_execution * fee


def attach_returns(trades: pd.DataFrame) -> pd.DataFrame:
    output = trades.copy()
    for scenario, assumptions in CONFIG["costs"].items():
        vbt_return = vectorbt_short_returns(output, assumptions["fee_per_side"], assumptions["slippage_per_side"])
        manual = output.apply(
            manual_short_return, axis=1, fee=assumptions["fee_per_side"], slippage=assumptions["slippage_per_side"],
        ).to_numpy(float)
        output[f"{scenario}_price_cost_return"] = vbt_return
        output[f"{scenario}_reconciliation_error"] = vbt_return - manual
        funding_column = "stress_funding_return" if assumptions["funding_stress"] else "actual_funding_return"
        output[f"{scenario}_net_return"] = vbt_return + output[funding_column].to_numpy(float)
    return output


def weekly_returns(trades: pd.DataFrame, column: str) -> pd.Series:
    return trades.groupby("entry_time")[column].sum().sort_index()


def daily_equity(trades: pd.DataFrame, bars: dict[str, pd.DataFrame], funding: dict[str, pd.DataFrame], scenario: str) -> pd.Series:
    assumptions = CONFIG["costs"][scenario]
    fee = float(assumptions["fee_per_side"])
    slippage = float(assumptions["slippage_per_side"])
    global_capital = 1.0
    points: dict[pd.Timestamp, float] = {}
    for entry, legs in trades.groupby("entry_time", sort=True):
        exit_time = legs["exit_time"].iloc[0]
        normalized_by_day: dict[pd.Timestamp, float] = {}
        for _, row in legs.iterrows():
            symbol = row["symbol"]
            quantity = float(row["quantity_per_unit_plan_capital"])
            entry_execution = float(row["entry_price"]) * (1.0 - slippage)
            entry_fee = quantity * entry_execution * fee
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index <= exit_time)].copy()
            if assumptions["funding_stress"]:
                rates["fundingRate"] = rates["fundingRate"].map(stressed_short_rate)
            days = bars[symbol][(bars[symbol].index >= entry) & (bars[symbol].index < exit_time)]
            for day, bar in days.iterrows():
                settled = rates[rates.index < day + pd.Timedelta(days=1)]
                funding_cashflow = float((quantity * settled["markPrice"] * settled["fundingRate"]).sum())
                leg_equity_change = quantity * (entry_execution - float(bar["close"])) - entry_fee + funding_cashflow
                normalized_by_day[day] = normalized_by_day.get(day, 1.0) + leg_equity_change
        for day, normalized in normalized_by_day.items():
            points[day] = global_capital * normalized
        global_capital *= 1.0 + float(legs[f"{scenario}_net_return"].sum())
    return pd.Series(points, dtype="float64").sort_index()


def block_bootstrap_mean_ci(values: np.ndarray, block: int = 4, reps: int = 5000, seed: int = 20260722) -> list[float]:
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(reps)
    for index in range(reps):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(block)) % len(values)).tolist())
        means[index] = values[np.asarray(chosen[: len(values)])].mean()
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def hurdle_adjust(total: float, start: pd.Timestamp, end: pd.Timestamp) -> float:
    years = (end - start).days / 365.0
    return (1.0 + total) / ((1.0 + float(CONFIG["annual_capital_hurdle"])) ** years) - 1.0


def summarize(
    trades: pd.DataFrame, bars: dict[str, pd.DataFrame], funding: dict[str, pd.DataFrame],
    stage: str, market_gross: pd.Series | None = None,
) -> dict[str, Any]:
    start, end = map(pd.Timestamp, STAGES[stage])
    result: dict[str, Any] = {
        "weeks": int(trades["entry_time"].nunique()), "legs": int(len(trades)),
        "funding_events": int(trades["funding_events"].sum()),
        "selection_counts": {k: int(v) for k, v in trades["symbol"].value_counts().reindex(SYMBOLS, fill_value=0).items()},
        "maximum_vectorbt_reconciliation_error": float(max(
            trades[f"{scenario}_reconciliation_error"].abs().max() for scenario in CONFIG["costs"]
        )),
        "by_year": {}, "by_symbol": {}, "scenarios": {},
    }
    for scenario in CONFIG["costs"]:
        weekly = weekly_returns(trades, f"{scenario}_net_return")
        equity = daily_equity(trades, bars, funding, scenario)
        total = float(np.prod(1.0 + weekly.to_numpy(float)) - 1.0)
        running_max = equity.cummax().clip(lower=1.0)
        max_drawdown = float((equity / running_max - 1.0).min())
        result["scenarios"][scenario] = {
            "total_return": total,
            "annualized_return": float((1.0 + total) ** (365.0 / (end - start).days) - 1.0),
            "daily_max_drawdown": max_drawdown,
            "weekly_mean_bootstrap_95pct": block_bootstrap_mean_ci(weekly.to_numpy(float)),
            "return_after_4pct_annual_hurdle": hurdle_adjust(total, start, end),
            "arithmetic_sum": float(weekly.sum()),
        }
    base_weekly = weekly_returns(trades, "base_net_return")
    for year, values in base_weekly.groupby(base_weekly.index.year):
        result["by_year"][str(year)] = float(np.prod(1.0 + values.to_numpy(float)) - 1.0)
    symbol_pnl = trades.groupby("symbol")["base_net_return"].sum().reindex(SYMBOLS, fill_value=0.0)
    positive_sum = float(symbol_pnl.clip(lower=0.0).sum())
    result["by_symbol"] = {symbol: float(value) for symbol, value in symbol_pnl.items()}
    result["largest_positive_pnl_share"] = float(symbol_pnl.clip(lower=0.0).max() / positive_sum) if positive_sum > 0 else 1.0
    if market_gross is not None:
        selected_gross = weekly_returns(trades, "gross_short_return")
        selection = selected_gross - market_gross.reindex(selected_gross.index)
        result["gross_selection_return"] = {
            "mean": float(selection.mean()), "total_arithmetic": float(selection.sum()),
            "bootstrap_95pct": block_bootstrap_mean_ci(selection.to_numpy(float)),
            "positive_weeks_fraction": float((selection > 0).mean()),
        }
    return result


def stage_authorized(stage: str) -> None:
    prior = {"evaluation": "development", "confirmation": "evaluation"}.get(stage)
    if prior and read_json(HERE / f"{prior}_gate.json")["status"] != "PASS":
        raise RuntimeError(f"{stage} not authorized")


def command_analyze(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    stage_authorized(args.stage)
    if read_json(HERE / "data_quality.json")["status"] != "PASS":
        raise RuntimeError("data quality is not PASS")
    bars, funding = load_all()
    main = attach_returns(build_trades(bars, funding, args.stage, 7, 1))
    formation_14 = attach_returns(build_trades(bars, funding, args.stage, 14, 1))
    bottom_2 = attach_returns(build_trades(bars, funding, args.stage, 7, 2))
    market = attach_returns(build_trades(bars, funding, args.stage, 7, 6))
    btc = attach_returns(build_trades(bars, funding, args.stage, 7, 1, fixed_symbols=["BTCUSDT"]))
    market_gross = weekly_returns(market, "gross_short_return")
    main.to_csv(HERE / f"{args.stage}_trades.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at_utc": iso_now(), "stage": args.stage,
        "period": {"start": STAGES[args.stage][0], "end_exclusive": STAGES[args.stage][1]},
        "main": summarize(main, bars, funding, args.stage, market_gross),
        "diagnostics": {
            "formation_14d": summarize(formation_14, bars, funding, args.stage, market_gross),
            "bottom_2": summarize(bottom_2, bars, funding, args.stage, market_gross),
            "equal_weight_short": summarize(market, bars, funding, args.stage),
            "btc_short": summarize(btc, bars, funding, args.stage),
        },
        "search_disclosure": {"selectable_primary_configurations": 1, "diagnostics_not_selectable": 4},
        "trade_csv_sha256": sha256_file(HERE / f"{args.stage}_trades.csv"),
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / f"{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage, "weeks": payload["main"]["weeks"],
        "base_total": payload["main"]["scenarios"]["base"]["total_return"],
        "selection_mean": payload["main"]["gross_selection_return"]["mean"],
    }))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    main = result["main"]
    scenarios = main["scenarios"]
    checks = {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "vectorbt_reconciled": main["maximum_vectorbt_reconciliation_error"] <= 1e-10,
        "base_total_positive": scenarios["base"]["total_return"] > 0,
        "stress_total_positive": scenarios["stress"]["total_return"] > 0,
        "stress_after_hurdle_positive": scenarios["stress"]["return_after_4pct_annual_hurdle"] > 0,
        "selection_mean_positive": main["gross_selection_return"]["mean"] > 0,
        "at_least_four_symbols_selected": sum(value > 0 for value in main["selection_counts"].values()) >= 4,
    }
    if stage == "confirmation":
        checks.update({
            "weeks_at_least_20": main["weeks"] >= 20,
            "daily_drawdown_above_minus_10pct": scenarios["base"]["daily_max_drawdown"] > -0.10,
        })
    else:
        checks.update({
            "weeks_at_least_100": main["weeks"] >= 100,
            "each_full_year_base_positive": all(value > 0 for value in main["by_year"].values()),
            "daily_drawdown_above_minus_15pct": scenarios["base"]["daily_max_drawdown"] > -0.15,
            "selection_bootstrap_lower_positive": main["gross_selection_return"]["bootstrap_95pct"][0] > 0,
            "four_symbols_selected_at_least_five_times": sum(value >= 5 for value in main["selection_counts"].values()) >= 4,
            "largest_positive_pnl_share_at_most_half": main["largest_positive_pnl_share"] <= 0.50,
            "beats_equal_weight_short_base": scenarios["base"]["total_return"] > result["diagnostics"]["equal_weight_short"]["scenarios"]["base"]["total_return"],
        })
    return checks


def command_gate(args: argparse.Namespace) -> None:
    result = read_json(HERE / f"{args.stage}.json")
    checks = gate_checks(args.stage, result)
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "generated_at_utc": iso_now(), "stage": args.stage, "status": status,
        "checks": checks, "failed_checks": [key for key, value in checks.items() if not value],
        "result_digest": result["content_digest"],
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / f"{args.stage}_gate.json", payload)
    if status == "FAIL":
        raw_positive = result["main"]["scenarios"]["base"]["total_return"] > 0 and result["main"]["scenarios"]["stress"]["total_return"] > 0
        conclusion = "INSUFFICIENT_EVIDENCE" if raw_positive else "DOES_NOT_SUPPORT"
        stopped = {
            "generated_at_utc": iso_now(), "conclusion": conclusion,
            "stopped_after": args.stage, "gate_status": status, "failed_checks": payload["failed_checks"],
            "main": result["main"], "diagnostics": result["diagnostics"],
            "later_stages": "NOT_OPENED_BY_SEQUENTIAL_GATE", "handoff": "NOT_GENERATED", "product_effects": "NONE",
        }
        stopped["content_digest"] = canonical_digest(stopped)
        write_json(HERE / "results.json", stopped)
    print(json.dumps({"stage": args.stage, "status": status, "failed": payload["failed_checks"]}))


def command_conclude(_args: argparse.Namespace) -> None:
    stages = {stage: read_json(HERE / f"{stage}.json") for stage in STAGES}
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in STAGES}
    all_pass = all(gate["status"] == "PASS" for gate in gates.values())
    confirmation = stages["confirmation"]
    payload = {
        "generated_at_utc": iso_now(),
        "conclusion": "SUPPORTS_WITHIN_SCOPE" if all_pass else "INSUFFICIENT_EVIDENCE",
        "stage_gates": {stage: gate["status"] for stage, gate in gates.items()},
        "stage_main": {stage: result["main"] for stage, result in stages.items()},
        "confirmation_diagnostics": confirmation["diagnostics"],
        "claim_limit": "Fixed six-survivor Binance USD-M weekly bottom-1 short under recorded costs; no long-term profit guarantee.",
        "product_effects": "NONE",
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / "results.json", payload)
    print(json.dumps({"conclusion": payload["conclusion"]}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Liquid-perp weekly loser continuation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    subparsers.add_parser("fetch").set_defaults(func=command_fetch)
    subparsers.add_parser("inspect").set_defaults(func=command_inspect)
    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--stage", choices=tuple(STAGES), required=True)
    analyze.set_defaults(func=command_analyze)
    gate = subparsers.add_parser("gate")
    gate.add_argument("--stage", choices=tuple(STAGES), required=True)
    gate.set_defaults(func=command_gate)
    subparsers.add_parser("conclude").set_defaults(func=command_conclude)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
