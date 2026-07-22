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
CACHE_ROOT = Path(
    os.environ.get(
        "HALPHA_TRX_PERP_VOLTARGET_CACHE",
        "D:/projects/Codex/CodexHome/research-data/halpha/"
        "trxusdt-perp-monthly-one-shot-voltarget/2026-07-22-v1",
    )
)
BASE_URL = "https://fapi.binance.com"
SYMBOL = "TRXUSDT"
DATA_START = "2020-10-01T00:00:00Z"
DATA_END_EXCLUSIVE = "2026-07-02T00:00:00Z"
RESEARCH_CUTOFF = "2026-07-01T00:00:00Z"
STAGES = {
    "development": ("2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
CONFIG = {
    "strategy_id": "RESEARCH_TRXUSDT_PERP_VOL60_TARGET8_MONTHLY_ONE_SHOT_V1",
    "volatility_lookback_days": 60,
    "target_volatilities": [0.06, 0.08, 0.10],
    "primary_target_volatility": 0.08,
    "maximum_notional_fraction": 0.5,
    "annual_capital_hurdle": 0.04,
    "costs": {
        "favorable": {
            "fee_per_side": 0.0006,
            "slippage_per_side": 0.0,
            "funding_stress": False,
        },
        "base": {
            "fee_per_side": 0.0006,
            "slippage_per_side": 0.0010,
            "funding_stress": False,
        },
        "stress": {
            "fee_per_side": 0.0006,
            "slippage_per_side": 0.0020,
            "funding_stress": True,
        },
    },
    "funding_stress": {
        "positive_rate_multiplier": 1.5,
        "negative_rate_multiplier": 0.5,
    },
    "stage_open_rule": (
        "development first; evaluation only after development gate PASS; "
        "confirmation only after evaluation gate PASS"
    ),
}
PARENT_RESULT = HERE.parents[2] / "legacy/2026/trxusdt-voltarget-8pct-long/results.json"


def utc_ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1000)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256_bytes(raw)


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
    parent = read_json(PARENT_RESULT)
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {"id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1"},
        "research_kind": "STRATEGY_CANDIDATE",
        "question": (
            "Does the fresh-confirmed TRX spot 8% volatility target remain economically "
            "portable to one-shot monthly Binance USD-M plans after actual funding and forced round trips?"
        ),
        "evidence_boundary": (
            "All parent spot price periods are exposed. Perpetual funding and forced one-shot closure "
            "results are unviewed. This audits portability, not new independent price-time evidence."
        ),
        "symbol": SYMBOL,
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "research_cutoff": RESEARCH_CUTOFF,
        "stages": STAGES,
        "config": CONFIG,
        "parent_result_path": str(PARENT_RESULT),
        "parent_result_sha256": sha256_file(PARENT_RESULT),
        "parent_conclusion": parent["conclusion"],
        "study_py_sha256": sha256_file(Path(__file__)),
        "preregistration_sha256": sha256_file(HERE / "preregistration.md"),
        "sources_sha256": sha256_file(HERE / "sources.md"),
        "environment": {
            "python": platform.python_version(),
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "cache_root": str(CACHE_ROOT),
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"checkpoint": str(HERE / "checkpoint.json"), "digest": payload["content_digest"]}))


def ensure_checkpoint() -> dict[str, Any]:
    path = HERE / "checkpoint.json"
    if not path.exists():
        raise RuntimeError("checkpoint.json missing; run checkpoint before data access")
    checkpoint = read_json(path)
    if checkpoint["config"] != CONFIG or checkpoint["symbol"] != SYMBOL:
        raise RuntimeError("checkpoint no longer matches fixed configuration")
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
            "url": url,
            "path": str(path),
            "bytes": len(raw),
            "sha256": sha256_bytes(raw),
            "rows": len(rows),
            "first_time_ms": first,
            "last_time_ms": last,
        })
        if last + 1 <= cursor:
            raise RuntimeError(f"non-advancing pagination: {endpoint}")
        cursor = last + 1
        page_number += 1
        time.sleep(0.08)
    return pages


def command_fetch(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    raw_root = CACHE_ROOT / SYMBOL / "raw"
    klines = fetch_pages("/fapi/v1/klines", {"symbol": SYMBOL, "interval": "1d"}, "openTime", 1500, raw_root / "klines")
    mark_klines = fetch_pages(
        "/fapi/v1/markPriceKlines",
        {"symbol": SYMBOL, "interval": "8h"},
        "openTime",
        1500,
        raw_root / "mark-price-klines-with-prior-boundary",
        start_value="2020-09-30T16:00:00Z",
    )
    funding = fetch_pages("/fapi/v1/fundingRate", {"symbol": SYMBOL}, "fundingTime", 1000, raw_root / "funding")
    exchange_raw, exchange_url = request_json("/fapi/v1/exchangeInfo")
    exchange_path = raw_root / "exchangeInfo.json"
    if exchange_path.exists() and exchange_path.read_bytes() != exchange_raw:
        timestamped = raw_root / f"exchangeInfo-{pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
        timestamped.write_bytes(exchange_raw)
        exchange_path = timestamped
    elif not exchange_path.exists():
        exchange_path.parent.mkdir(parents=True, exist_ok=True)
        exchange_path.write_bytes(exchange_raw)
    manifest = {
        "accessed_at_utc": iso_now(),
        "checkpoint_digest": checkpoint["content_digest"],
        "source": "Binance public USD-M REST market data; no credentials",
        "symbol": SYMBOL,
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "kline_pages": klines,
        "mark_price_kline_pages": mark_klines,
        "funding_pages": funding,
        "exchange_info": {
            "url": exchange_url,
            "path": str(exchange_path),
            "bytes": len(exchange_raw),
            "sha256": sha256_bytes(exchange_raw),
        },
    }
    manifest["content_digest"] = canonical_digest(manifest)
    write_json(HERE / "source_manifest.json", manifest)
    print(json.dumps({"klines": len(klines), "mark_klines": len(mark_klines), "funding": len(funding), "digest": manifest["content_digest"]}))


def load_rows(items: list[dict[str, Any]]) -> list[Any]:
    rows: list[Any] = []
    for item in items:
        path = Path(item["path"])
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or sha256_bytes(raw) != item["sha256"]:
            raise RuntimeError(f"source identity mismatch: {path}")
        rows.extend(json.loads(raw))
    return rows


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    manifest = read_json(HERE / "source_manifest.json")
    krows = load_rows(manifest["kline_pages"])
    bars = pd.DataFrame(krows, columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trade_count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
    ])
    bars["open_time"] = pd.to_datetime(bars["open_time"], unit="ms", utc=True)
    for column in ["open", "high", "low", "close", "volume", "quote_volume"]:
        bars[column] = pd.to_numeric(bars[column], errors="raise")
    bars = bars.drop_duplicates("open_time", keep="last").sort_values("open_time").set_index("open_time")

    frows = load_rows(manifest["funding_pages"])
    funding = pd.DataFrame(frows)
    funding["fundingTime"] = pd.to_datetime(funding["fundingTime"], unit="ms", utc=True)
    funding["fundingRate"] = pd.to_numeric(funding["fundingRate"], errors="raise")
    funding["markPrice"] = pd.to_numeric(funding["markPrice"], errors="coerce")
    funding = funding.drop_duplicates("fundingTime", keep="last").sort_values("fundingTime").set_index("fundingTime")

    mark_rows = load_rows(manifest["mark_price_kline_pages"])
    marks = pd.DataFrame(mark_rows, columns=[
        "open_time", "open", "high", "low", "close", "ignore_volume", "close_time",
        "ignore_quote_volume", "ignore_count", "ignore_taker_base", "ignore_taker_quote", "ignore",
    ])
    marks["close_time"] = pd.to_datetime(marks["close_time"], unit="ms", utc=True)
    marks["close"] = pd.to_numeric(marks["close"], errors="raise")
    marks = marks.drop_duplicates("close_time", keep="last").sort_values("close_time")
    funding_reset = funding.reset_index()
    matched = pd.merge_asof(
        funding_reset.sort_values("fundingTime"),
        marks[["close_time", "close"]],
        left_on="fundingTime",
        right_on="close_time",
        direction="nearest",
        tolerance=pd.Timedelta(minutes=1),
    )
    funding_reset["mark_price_from_funding_response"] = funding_reset["markPrice"].notna()
    funding_reset["mark_price_match_delta_ms"] = (
        matched["close_time"] - matched["fundingTime"]
    ).dt.total_seconds() * 1000.0
    funding_reset["markPrice"] = funding_reset["markPrice"].fillna(matched["close"])
    funding = funding_reset.set_index("fundingTime").sort_index()

    exchange_item = manifest["exchange_info"]
    exchange_raw = Path(exchange_item["path"]).read_bytes()
    if len(exchange_raw) != exchange_item["bytes"] or sha256_bytes(exchange_raw) != exchange_item["sha256"]:
        raise RuntimeError("exchange info identity mismatch")
    exchange = json.loads(exchange_raw)
    symbol_info = next(item for item in exchange["symbols"] if item["symbol"] == SYMBOL)
    return bars, funding, symbol_info


def command_inspect(_args: argparse.Namespace) -> None:
    ensure_checkpoint()
    bars, funding, symbol_info = load_data()
    expected = pd.date_range(pd.Timestamp(DATA_START), pd.Timestamp(DATA_END_EXCLUSIVE), freq="1D", inclusive="left")
    selected = bars[(bars.index >= expected[0]) & (bars.index < pd.Timestamp(DATA_END_EXCLUSIVE))]
    missing = expected.difference(selected.index)
    invalid = int(((selected[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
    invalid_range = int(((selected["high"] < selected[["open", "close"]].max(axis=1)) | (selected["low"] > selected[["open", "close"]].min(axis=1))).sum())
    selected_funding = funding[(funding.index >= pd.Timestamp(DATA_START)) & (funding.index <= pd.Timestamp(RESEARCH_CUTOFF))]
    funding_gaps = selected_funding.index.to_series().diff().dropna().dt.total_seconds() / 3600
    missing_mark = int(selected_funding["markPrice"].isna().sum())
    filled_mark = int((~selected_funding["mark_price_from_funding_response"]).sum())
    filters = {item["filterType"]: item for item in symbol_info["filters"]}
    status = "PASS" if len(missing) == 0 and invalid == 0 and invalid_range == 0 and len(selected_funding) > 5000 and missing_mark == 0 else "FAIL"
    payload = {
        "checked_at_utc": iso_now(),
        "status": status,
        "bars": {
            "rows": int(len(selected)),
            "first": selected.index.min().isoformat(),
            "last": selected.index.max().isoformat(),
            "missing": int(len(missing)),
            "duplicates": int(selected.index.duplicated().sum()),
            "invalid_ohlc": invalid,
            "invalid_range": invalid_range,
            "median_quote_volume": float(selected["quote_volume"].median()),
            "minimum_quote_volume": float(selected["quote_volume"].min()),
        },
        "funding": {
            "rows": int(len(selected_funding)),
            "first": selected_funding.index.min().isoformat(),
            "last": selected_funding.index.max().isoformat(),
            "missing_mark_price": missing_mark,
            "mark_price_from_funding_response": int(selected_funding["mark_price_from_funding_response"].sum()),
            "mark_price_filled_from_official_8h_kline": filled_mark,
            "maximum_absolute_mark_match_delta_ms": float(selected_funding["mark_price_match_delta_ms"].abs().max()),
            "maximum_gap_hours": float(funding_gaps.max()),
            "interval_hours_counts": {str(k): int(v) for k, v in funding_gaps.round(6).value_counts().sort_index().items()},
        },
        "current_exchange_snapshot": {
            "status": symbol_info["status"],
            "contract_type": symbol_info["contractType"],
            "onboard_date": pd.to_datetime(symbol_info["onboardDate"], unit="ms", utc=True).isoformat(),
            "price_filter": filters.get("PRICE_FILTER"),
            "lot_size": filters.get("LOT_SIZE"),
            "market_lot_size": filters.get("MARKET_LOT_SIZE"),
            "min_notional": filters.get("MIN_NOTIONAL"),
        },
        "source_manifest_sha256": sha256_file(HERE / "source_manifest.json"),
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / "data_quality.json", payload)
    print(json.dumps({"status": status, "bars": len(selected), "funding": len(selected_funding)}))
    if status != "PASS":
        raise RuntimeError("data quality failed")


def adverse_funding_rate(rate: float) -> float:
    if rate > 0:
        return rate * CONFIG["funding_stress"]["positive_rate_multiplier"]
    return rate * CONFIG["funding_stress"]["negative_rate_multiplier"]


def build_plans(bars: pd.DataFrame, funding: pd.DataFrame, stage: str, target: float) -> pd.DataFrame:
    start, end = map(pd.Timestamp, STAGES[stage])
    month_starts = pd.date_range(start, end, freq="MS", inclusive="left")
    rows: list[dict[str, Any]] = []
    lookback = int(CONFIG["volatility_lookback_days"])
    for entry in month_starts:
        exit_time = entry + pd.offsets.MonthBegin(1)
        decision = entry - pd.Timedelta(days=1)
        first_close = decision - pd.Timedelta(days=lookback)
        closes = bars.loc[(bars.index >= first_close) & (bars.index <= decision), "close"]
        if len(closes) != lookback + 1 or entry not in bars.index or exit_time not in bars.index:
            raise RuntimeError(f"incomplete plan input: {entry}")
        realized = float(np.log(closes).diff().dropna().std(ddof=1) * math.sqrt(365.0))
        if not math.isfinite(realized) or realized <= 0:
            raise RuntimeError(f"invalid realized volatility: {entry}")
        weight = min(float(CONFIG["maximum_notional_fraction"]), target / realized)
        rates = funding[(funding.index > entry) & (funding.index <= exit_time)]
        if rates.empty or rates["markPrice"].isna().any():
            raise RuntimeError(f"funding input incomplete: {entry}")
        entry_price = float(bars.at[entry, "open"])
        exit_price = float(bars.at[exit_time, "open"])
        quantity = weight / entry_price
        actual_funding = float((-quantity * rates["markPrice"] * rates["fundingRate"]).sum())
        stressed_rates = rates["fundingRate"].map(adverse_funding_rate)
        stress_funding = float((-quantity * rates["markPrice"] * stressed_rates).sum())
        rows.append({
            "plan_id": f"{stage}-{entry.strftime('%Y%m')}-{target:.2f}",
            "stage": stage,
            "entry_time": entry,
            "exit_time": exit_time,
            "decision_time": decision,
            "target_volatility": target,
            "realized_volatility_60d": realized,
            "weight": weight,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity_per_unit_plan_capital": quantity,
            "funding_events": int(len(rates)),
            "actual_funding_return": actual_funding,
            "stress_funding_return": stress_funding,
            "funding_rate_sum": float(rates["fundingRate"].sum()),
        })
    return pd.DataFrame(rows)


def vectorbt_price_cost_returns(plans: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    columns = plans["plan_id"].tolist()
    prices = pd.DataFrame(
        [plans["entry_price"].to_numpy(float), plans["exit_price"].to_numpy(float)],
        index=pd.Index([0, 1], name="step"),
        columns=columns,
    )
    quantities = plans["quantity_per_unit_plan_capital"].to_numpy(float)
    sizes = pd.DataFrame([quantities, -quantities], index=prices.index, columns=columns)
    portfolio = vbt.Portfolio.from_orders(
        prices,
        size=sizes,
        size_type="amount",
        fees=fee,
        slippage=slippage,
        init_cash=1.0,
        freq="1D",
    )
    return portfolio.total_return().reindex(columns).to_numpy(float)


def manual_price_cost_return(row: pd.Series, fee: float, slippage: float) -> float:
    quantity = float(row["quantity_per_unit_plan_capital"])
    entry = float(row["entry_price"]) * (1.0 + slippage)
    exit_price = float(row["exit_price"]) * (1.0 - slippage)
    return quantity * (exit_price - entry) - quantity * entry * fee - quantity * exit_price * fee


def attach_returns(plans: pd.DataFrame) -> pd.DataFrame:
    output = plans.copy()
    for scenario, assumptions in CONFIG["costs"].items():
        vbt_returns = vectorbt_price_cost_returns(output, assumptions["fee_per_side"], assumptions["slippage_per_side"])
        manual = output.apply(
            manual_price_cost_return,
            axis=1,
            fee=assumptions["fee_per_side"],
            slippage=assumptions["slippage_per_side"],
        ).to_numpy(float)
        output[f"{scenario}_vbt_price_cost_return"] = vbt_returns
        output[f"{scenario}_manual_price_cost_return"] = manual
        output[f"{scenario}_reconciliation_error"] = vbt_returns - manual
        funding_column = "stress_funding_return" if assumptions["funding_stress"] else "actual_funding_return"
        output[f"{scenario}_net_return"] = vbt_returns + output[funding_column].to_numpy(float)
    return output


def daily_equity(plans: pd.DataFrame, bars: pd.DataFrame, funding: pd.DataFrame, scenario: str) -> pd.Series:
    assumptions = CONFIG["costs"][scenario]
    fee = float(assumptions["fee_per_side"])
    slippage = float(assumptions["slippage_per_side"])
    global_capital = 1.0
    points: dict[pd.Timestamp, float] = {}
    for _, row in plans.iterrows():
        entry = row["entry_time"]
        exit_time = row["exit_time"]
        quantity = float(row["quantity_per_unit_plan_capital"])
        entry_execution = float(row["entry_price"]) * (1.0 + slippage)
        entry_fee = quantity * entry_execution * fee
        plan_funding = funding[(funding.index > entry) & (funding.index <= exit_time)].copy()
        if assumptions["funding_stress"]:
            plan_funding["fundingRate"] = plan_funding["fundingRate"].map(adverse_funding_rate)
        days = bars[(bars.index >= entry) & (bars.index < exit_time)]
        for day, bar in days.iterrows():
            cutoff = day + pd.Timedelta(days=1)
            settled = plan_funding[plan_funding.index < cutoff]
            funding_cashflow = float((-quantity * settled["markPrice"] * settled["fundingRate"]).sum())
            normalized = 1.0 + quantity * (float(bar["close"]) - entry_execution) - entry_fee + funding_cashflow
            points[day] = global_capital * normalized
        global_capital *= 1.0 + float(row[f"{scenario}_net_return"])
    return pd.Series(points, dtype="float64").sort_index()


def block_bootstrap_mean_ci(values: np.ndarray, block: int = 3, reps: int = 5000, seed: int = 20260722) -> list[float]:
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


def hurdle_adjust(total_return: float, start: pd.Timestamp, end: pd.Timestamp) -> float:
    years = (end - start).total_seconds() / (365.0 * 86400.0)
    return (1.0 + total_return) / ((1.0 + float(CONFIG["annual_capital_hurdle"])) ** years) - 1.0


def summarize(plans: pd.DataFrame, bars: pd.DataFrame, funding: pd.DataFrame, stage: str) -> dict[str, Any]:
    start, end = map(pd.Timestamp, STAGES[stage])
    result: dict[str, Any] = {
        "plans": int(len(plans)),
        "mean_weight": float(plans["weight"].mean()),
        "minimum_weight": float(plans["weight"].min()),
        "maximum_weight": float(plans["weight"].max()),
        "funding_events": int(plans["funding_events"].sum()),
        "actual_funding_return_arithmetic_sum": float(plans["actual_funding_return"].sum()),
        "stress_funding_return_arithmetic_sum": float(plans["stress_funding_return"].sum()),
        "maximum_vectorbt_reconciliation_error": float(max(
            plans[f"{name}_reconciliation_error"].abs().max() for name in CONFIG["costs"]
        )),
        "by_year": {},
        "scenarios": {},
    }
    for scenario in CONFIG["costs"]:
        monthly = plans[f"{scenario}_net_return"].to_numpy(float)
        equity = daily_equity(plans, bars, funding, scenario)
        daily_returns = pd.concat([pd.Series([1.0], index=[start - pd.Timedelta(days=1)]), equity]).pct_change().dropna()
        total = float(np.prod(1.0 + monthly) - 1.0)
        annualized = float((1.0 + total) ** (365.0 / (end - start).days) - 1.0)
        volatility = float(daily_returns.std(ddof=1) * math.sqrt(365.0))
        sharpe = float(daily_returns.mean() / daily_returns.std(ddof=1) * math.sqrt(365.0)) if daily_returns.std(ddof=1) > 0 else 0.0
        running_max = equity.cummax().clip(lower=1.0)
        max_drawdown = float((equity / running_max - 1.0).min())
        result["scenarios"][scenario] = {
            "total_return": total,
            "annualized_return": annualized,
            "annualized_volatility": volatility,
            "sharpe_zero_rf": sharpe,
            "daily_max_drawdown": max_drawdown,
            "monthly_mean_bootstrap_95pct": block_bootstrap_mean_ci(monthly),
            "return_after_4pct_annual_hurdle": hurdle_adjust(total, start, end),
        }
    for year, group in plans.groupby(plans["entry_time"].dt.year):
        result["by_year"][str(year)] = {
            scenario: float(np.prod(1.0 + group[f"{scenario}_net_return"].to_numpy(float)) - 1.0)
            for scenario in CONFIG["costs"]
        }
    return result


def stage_authorized(stage: str) -> None:
    if stage == "evaluation":
        gate = read_json(HERE / "development_gate.json")
        if gate["status"] != "PASS":
            raise RuntimeError("evaluation not authorized")
    if stage == "confirmation":
        gate = read_json(HERE / "evaluation_gate.json")
        if gate["status"] != "PASS":
            raise RuntimeError("confirmation not authorized")


def command_analyze(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    stage_authorized(args.stage)
    quality = read_json(HERE / "data_quality.json")
    if quality["status"] != "PASS":
        raise RuntimeError("data quality is not PASS")
    bars, funding, _symbol_info = load_data()
    matrices: dict[str, Any] = {}
    frames: dict[float, pd.DataFrame] = {}
    for target in CONFIG["target_volatilities"]:
        plans = attach_returns(build_plans(bars, funding, args.stage, float(target)))
        frames[float(target)] = plans
        matrices[f"{target:.2f}"] = summarize(plans, bars, funding, args.stage)
    benchmark = attach_returns(build_plans(bars, funding, args.stage, 10.0))
    benchmark["weight"] = float(CONFIG["maximum_notional_fraction"])
    benchmark["quantity_per_unit_plan_capital"] = benchmark["weight"] / benchmark["entry_price"]
    # Recompute funding and price/cost after replacing volatility-targeted quantities.
    raw_benchmark = build_fixed_weight_plans(benchmark, funding)
    benchmark = attach_returns(raw_benchmark)
    benchmark_summary = summarize(benchmark, bars, funding, args.stage)
    primary = frames[float(CONFIG["primary_target_volatility"])]
    primary.to_csv(HERE / f"{args.stage}_plans.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at_utc": iso_now(),
        "stage": args.stage,
        "period": {"start": STAGES[args.stage][0], "end_exclusive": STAGES[args.stage][1]},
        "data_quality_digest": quality["content_digest"],
        "matrix": matrices,
        "fixed_half_long_benchmark": benchmark_summary,
        "primary_plan_csv_sha256": sha256_file(HERE / f"{args.stage}_plans.csv"),
        "search_disclosure": {
            "selectable_primary_configurations": 1,
            "diagnostic_neighbor_targets": [0.06, 0.10],
            "simple_benchmark": "forced-monthly 0.5x long",
        },
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / f"{args.stage}.json", payload)
    main = matrices["0.08"]["scenarios"]["base"]
    print(json.dumps({"stage": args.stage, "base_total": main["total_return"], "max_drawdown": main["daily_max_drawdown"]}))


def build_fixed_weight_plans(plans: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    output = plans.copy()
    for index, row in output.iterrows():
        quantity = float(row["weight"]) / float(row["entry_price"])
        rates = funding[(funding.index > row["entry_time"]) & (funding.index <= row["exit_time"])]
        output.at[index, "quantity_per_unit_plan_capital"] = quantity
        output.at[index, "actual_funding_return"] = float((-quantity * rates["markPrice"] * rates["fundingRate"]).sum())
        stressed = rates["fundingRate"].map(adverse_funding_rate)
        output.at[index, "stress_funding_return"] = float((-quantity * rates["markPrice"] * stressed).sum())
    return output


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    primary = result["matrix"]["0.08"]["scenarios"]
    benchmark = result["fixed_half_long_benchmark"]["scenarios"]["base"]
    checks = {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "all_plans_present": result["matrix"]["0.08"]["plans"] == (24 if stage != "confirmation" else 18),
        "vectorbt_reconciled": result["matrix"]["0.08"]["maximum_vectorbt_reconciliation_error"] <= 1e-10,
        "base_total_positive": primary["base"]["total_return"] > 0,
        "stress_after_hurdle_positive": primary["stress"]["return_after_4pct_annual_hurdle"] > 0,
        "base_drawdown_better_than_half_long": primary["base"]["daily_max_drawdown"] > benchmark["daily_max_drawdown"],
        "neighbor_6pct_base_nonnegative": result["matrix"]["0.06"]["scenarios"]["base"]["total_return"] >= 0,
        "neighbor_10pct_base_nonnegative": result["matrix"]["0.10"]["scenarios"]["base"]["total_return"] >= 0,
    }
    if stage == "confirmation":
        checks.update({
            "stress_total_positive": primary["stress"]["total_return"] > 0,
            "daily_drawdown_above_minus_10pct": primary["base"]["daily_max_drawdown"] > -0.10,
            "each_entry_year_base_positive": all(
                values["base"] > 0 for values in result["matrix"]["0.08"]["by_year"].values()
            ),
        })
    else:
        checks["daily_drawdown_above_minus_14pct"] = primary["base"]["daily_max_drawdown"] > -0.14
    return checks


def command_gate(args: argparse.Namespace) -> None:
    result = read_json(HERE / f"{args.stage}.json")
    checks = gate_checks(args.stage, result)
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "generated_at_utc": iso_now(),
        "stage": args.stage,
        "status": status,
        "checks": checks,
        "failed_checks": [key for key, value in checks.items() if not value],
        "result_digest": result["content_digest"],
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / f"{args.stage}_gate.json", payload)
    print(json.dumps({"stage": args.stage, "status": status, "failed": payload["failed_checks"]}))


def command_conclude(_args: argparse.Namespace) -> None:
    stages = {stage: read_json(HERE / f"{stage}.json") for stage in STAGES}
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in STAGES}
    parent = read_json(PARENT_RESULT)
    all_pass = all(gate["status"] == "PASS" for gate in gates.values())
    confirmation_total = stages["confirmation"]["matrix"]["0.08"]["scenarios"]["base"]["total_return"]
    if all_pass and parent["conclusion"] == "SUPPORTS_WITHIN_SCOPE":
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif confirmation_total <= 0:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    payload = {
        "generated_at_utc": iso_now(),
        "conclusion": conclusion,
        "claim": (
            "contract-and-one-shot-plan portability of the parent TRX spot volatility target; "
            "not new independent price-time alpha evidence"
        ),
        "stage_gate_status": {stage: gate["status"] for stage, gate in gates.items()},
        "stage_primary": {
            stage: result["matrix"]["0.08"] for stage, result in stages.items()
        },
        "stage_half_long_benchmark": {
            stage: result["fixed_half_long_benchmark"] for stage, result in stages.items()
        },
        "parent_conclusion": parent["conclusion"],
        "parent_result_sha256": sha256_file(PARENT_RESULT),
        "evidence_limit": (
            "Parent spot price outcomes were exposed before this study. A pass inherits the parent's fresh "
            "spot confirmation and adds only previously unviewed perpetual funding/forced-closure evidence."
        ),
        "product_effects": "NONE",
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / "results.json", payload)
    write_decision_trace(stages["confirmation"])
    print(json.dumps({"conclusion": conclusion, "all_gates_pass": all_pass}))


def write_decision_trace(confirmation: dict[str, Any]) -> None:
    plans = pd.read_csv(HERE / "confirmation_plans.csv")
    normal = plans.iloc[0]
    trace = {
        "strategy_id": CONFIG["strategy_id"],
        "schema": "framework-neutral research decision trace v1",
        "cases": [
            {
                "case": "normal_complete_input",
                "input": {
                    "instrument": "TRXUSDT-PERP",
                    "direction": "LONG",
                    "plan_amount_reference": "1000 USDT",
                    "decision_time": normal["decision_time"],
                    "realized_volatility_60d": float(normal["realized_volatility_60d"]),
                    "daily_history_complete": True,
                },
                "decision": {
                    "condition": "TRUE",
                    "target_notional": round(float(normal["weight"]) * 1000.0, 8),
                    "next_action_time": normal["entry_time"],
                    "exit_time": normal["exit_time"],
                    "add_or_reenter": False,
                },
            },
            {
                "case": "missing_warmup",
                "input": {"daily_returns_available": 59, "required": 60},
                "decision": {"condition": "UNKNOWN", "proposal": None, "reason": "VOLATILITY_WARMUP_INCOMPLETE"},
            },
            {
                "case": "expired_month_open_window",
                "input": {"decision_input_complete": True, "proposal_window_current": False},
                "decision": {"condition": "UNKNOWN", "proposal": None, "reason": "PROPOSAL_WINDOW_EXPIRED"},
            },
            {
                "case": "plan_amount_too_small_for_current_min_notional",
                "input": {"plan_amount_reference": "unknown or insufficient", "venue_rules_current": True},
                "decision": {"condition": "UNKNOWN", "proposal": None, "reason": "QUANTIZED_NOTIONAL_NOT_VENUE_ELIGIBLE"},
            },
        ],
        "limitations": [
            "No price stop; maximum 0.5x reference notional and one-month time exit are the fixed protection.",
            "Product qualification must prove plan amount can serve as the same capital reference.",
            "This trace is not a product object and authorizes no order.",
        ],
    }
    trace["content_digest"] = canonical_digest(trace)
    write_json(HERE / "decision_trace.json", trace)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TRXUSDT perpetual one-shot monthly volatility-target portability")
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
