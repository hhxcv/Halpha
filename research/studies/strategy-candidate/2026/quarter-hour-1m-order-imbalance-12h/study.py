from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import platform
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
CACHE = Path(r"D:\projects\Codex\CodexHome\research-data\halpha\quarter-hour-1m-order-imbalance-12h\2026-07-22-v1")
BASELINE = "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"]
DATA_START = pd.Timestamp("2024-10-01T00:00:00Z")
DATA_END = pd.Timestamp("2026-07-01T00:00:00Z")
STAGES = {
    "development": (pd.Timestamp("2024-11-01T00:00:00Z"), pd.Timestamp("2025-07-01T00:00:00Z")),
    "evaluation": (pd.Timestamp("2025-07-01T00:00:00Z"), pd.Timestamp("2026-01-01T00:00:00Z")),
    "confirmation": (pd.Timestamp("2026-01-01T00:00:00Z"), pd.Timestamp("2026-07-01T00:00:00Z")),
}
CONFIG = {
    "strategy_id": "RESEARCH_QH_1M_TAKER_IMBALANCE_12H_0P25X_V1",
    "signal_hours": [0, 12],
    "signal_minute": 15,
    "placebo_minute": 22,
    "rolling_observations": 60,
    "lower_quantile": 0.25,
    "upper_quantile": 0.75,
    "hold_hours": 12,
    "notional_fraction": 0.25,
    "annual_capital_hurdle": 0.04,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
}
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
    "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    body = dict(payload)
    digest_source = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    body["content_digest"] = hashlib.sha256(digest_source).hexdigest()
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def months() -> list[str]:
    return [str(period) for period in pd.period_range(DATA_START.tz_localize(None).to_period("M"),
                                                        (DATA_END - pd.Timedelta(minutes=1)).tz_localize(None).to_period("M"), freq="M")]


def retry_bytes(url: str, attempts: int = 5, timeout: int = 90) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Halpha-research/1.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # network failures are recorded by caller
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 8))
    assert last_error is not None
    raise last_error


def cached_download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    data = retry_bytes(url)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(data)
    temporary.replace(path)


def fetch_json_pages(symbol: str, endpoint: str, prefix: str, limit: int) -> list[dict]:
    start_ms = int(DATA_START.timestamp() * 1000)
    end_ms = int(DATA_END.timestamp() * 1000) - 1
    entries: list[dict] = []
    page = 1
    cursor = start_ms
    while cursor <= end_ms:
        params = {"symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": limit}
        if endpoint.endswith("markPriceKlines"):
            params["interval"] = "8h"
        url = "https://fapi.binance.com" + endpoint + "?" + urllib.parse.urlencode(params)
        path = CACHE / "rest" / f"{prefix}_{symbol}_{page:03d}.json"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(retry_bytes(url))
        data = json.loads(path.read_text(encoding="utf-8"))
        entries.append({"path": path, "url": url, "rows": len(data)})
        if not data or len(data) < limit:
            break
        raw_time = data[-1][0] if endpoint.endswith("markPriceKlines") else data[-1]["fundingTime"]
        next_cursor = int(raw_time) + 1
        if next_cursor <= cursor:
            raise RuntimeError(f"pagination did not advance for {symbol} {endpoint}")
        cursor = next_cursor
        page += 1
    return entries


def checkpoint() -> None:
    import scipy

    payload = {
        "created_at_utc": utc_now(),
        "baseline_commit": BASELINE,
        "formal_strategy": {"id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1"},
        "research_kind": "STRATEGY_CANDIDATE",
        "question": "Does a maintainable 1-minute proxy for quarter-hour opening order imbalance predict tradeable 12-hour USD-M returns after costs and funding?",
        "evidence_boundary": "The source paper ends 2024-10-31. Other paths on these assets are exposed; this exact 1m proxy and staged economic output are unviewed.",
        "symbols": SYMBOLS,
        "data_start": DATA_START.isoformat(),
        "data_end_exclusive": DATA_END.isoformat(),
        "stages": {key: [value[0].isoformat(), value[1].isoformat()] for key, value in STAGES.items()},
        "config": CONFIG,
        "study_py_sha256": sha256(HERE / "study.py"),
        "preregistration_sha256": sha256(HERE / "preregistration.md"),
        "sources_sha256": sha256(HERE / "sources.md"),
        "environment": {
            "python": platform.python_version(), "vectorbt": vbt.__version__, "pandas": pd.__version__,
            "numpy": np.__version__, "scipy": scipy.__version__,
        },
        "cache_root": str(CACHE),
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"checkpoint": "PASS", "study_sha256": payload["study_py_sha256"]}))


def verify_checkpoint() -> None:
    payload = read_json(HERE / "checkpoint.json")
    expected = {
        "study.py": payload["study_py_sha256"],
        "preregistration.md": payload["preregistration_sha256"],
        "sources.md": payload["sources_sha256"],
    }
    mismatches = {name: [digest, sha256(HERE / name)] for name, digest in expected.items() if sha256(HERE / name) != digest}
    if mismatches:
        raise RuntimeError(f"checkpoint mismatch: {mismatches}")


def fetch() -> None:
    verify_checkpoint()
    entries: list[dict] = []
    for symbol in SYMBOLS:
        for month in months():
            name = f"{symbol}-1m-{month}.zip"
            base_url = f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/1m/{name}"
            zip_path = CACHE / "klines" / symbol / name
            checksum_path = zip_path.with_suffix(zip_path.suffix + ".CHECKSUM")
            cached_download(base_url, zip_path)
            cached_download(base_url + ".CHECKSUM", checksum_path)
            official = checksum_path.read_text(encoding="utf-8").strip().split()[0].lower()
            actual = sha256(zip_path)
            if actual != official:
                raise RuntimeError(f"official checksum mismatch: {zip_path}")
            entries.extend([
                {"kind": "kline_zip", "symbol": symbol, "month": month, "url": base_url,
                 "path": str(zip_path), "bytes": zip_path.stat().st_size, "sha256": actual, "official_sha256": official},
                {"kind": "checksum", "symbol": symbol, "month": month, "url": base_url + ".CHECKSUM",
                 "path": str(checksum_path), "bytes": checksum_path.stat().st_size, "sha256": sha256(checksum_path)},
            ])
        for item in fetch_json_pages(symbol, "/fapi/v1/fundingRate", "funding", 1000):
            entries.append({"kind": "funding", "symbol": symbol, "url": item["url"], "path": str(item["path"]),
                            "rows": item["rows"], "bytes": item["path"].stat().st_size, "sha256": sha256(item["path"])})
        for item in fetch_json_pages(symbol, "/fapi/v1/markPriceKlines", "mark8h", 1500):
            entries.append({"kind": "mark8h", "symbol": symbol, "url": item["url"], "path": str(item["path"]),
                            "rows": item["rows"], "bytes": item["path"].stat().st_size, "sha256": sha256(item["path"])})
    write_json(HERE / "source_manifest.json", {
        "generated_at_utc": utc_now(), "access_date": "2026-07-22", "files": entries,
        "file_count": len(entries), "total_bytes": sum(int(item["bytes"]) for item in entries),
        "large_data_location": str(CACHE), "git_persistence": "RAW_DATA_OUTSIDE_GIT",
    })
    print(json.dumps({"files": len(entries), "bytes": sum(int(item["bytes"]) for item in entries)}))


def normalize_epoch(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.dropna().median() > 100_000_000_000_000:
        numeric = numeric / 1000.0
    return pd.to_datetime(numeric, unit="ms", utc=True, errors="coerce")


def load_bars(symbol: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for month in months():
        path = CACHE / "klines" / symbol / f"{symbol}-1m-{month}.zip"
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(members) != 1:
                raise RuntimeError(f"unexpected archive members: {path}: {members}")
            frame = pd.read_csv(archive.open(members[0]), header=None, names=KLINE_COLUMNS, dtype=str)
        frame["time"] = normalize_epoch(frame["open_time"])
        frame = frame.dropna(subset=["time"])
        for column in ["open", "high", "low", "close", "quote_volume", "taker_buy_quote"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frames.append(frame[["time", "open", "high", "low", "close", "quote_volume", "taker_buy_quote"]])
    output = pd.concat(frames, ignore_index=True).drop_duplicates("time", keep="last").sort_values("time")
    return output.set_index("time")


def load_funding(symbol: str) -> pd.DataFrame:
    funding_rows: list[dict] = []
    mark_rows: list[list] = []
    for path in sorted((CACHE / "rest").glob(f"funding_{symbol}_*.json")):
        funding_rows.extend(json.loads(path.read_text(encoding="utf-8")))
    for path in sorted((CACHE / "rest").glob(f"mark8h_{symbol}_*.json")):
        mark_rows.extend(json.loads(path.read_text(encoding="utf-8")))
    funding = pd.DataFrame(funding_rows)
    funding["time"] = pd.to_datetime(pd.to_numeric(funding["fundingTime"]), unit="ms", utc=True)
    funding["fundingRate"] = pd.to_numeric(funding["fundingRate"], errors="coerce")
    funding["markPrice"] = pd.to_numeric(funding.get("markPrice"), errors="coerce")
    marks = pd.DataFrame(mark_rows)
    mark_map = pd.DataFrame({
        "time": pd.to_datetime(pd.to_numeric(marks[0]), unit="ms", utc=True),
        "official_mark": pd.to_numeric(marks[4], errors="coerce"),
    }).drop_duplicates("time").sort_values("time")
    funding = funding.sort_values("time").drop_duplicates("time")
    merged = pd.merge_asof(funding, mark_map, on="time", direction="nearest", tolerance=pd.Timedelta(minutes=1))
    merged["markPrice"] = merged["markPrice"].fillna(merged["official_mark"])
    return merged.set_index("time")[["fundingRate", "markPrice"]]


def inspect() -> None:
    verify_checkpoint()
    manifest = read_json(HERE / "source_manifest.json")
    manifest_bad = []
    for item in manifest["files"]:
        path = Path(item["path"])
        if not path.exists() or sha256(path) != item["sha256"]:
            manifest_bad.append(str(path))
    expected_rows = int((DATA_END - DATA_START) / pd.Timedelta(minutes=1))
    symbols: dict[str, dict] = {}
    overall = not manifest_bad
    for symbol in SYMBOLS:
        bars = load_bars(symbol)
        funding = load_funding(symbol)
        expected_index = pd.date_range(DATA_START, DATA_END, freq="1min", inclusive="left")
        missing = int(len(expected_index.difference(bars.index)))
        extras = int(len(bars.index.difference(expected_index)))
        ohlc_bad = int(((bars[["open", "high", "low", "close"]].isna().any(axis=1)) |
                        (bars[["open", "high", "low", "close"]] <= 0).any(axis=1) |
                        (bars["high"] < bars[["open", "close", "low"]].max(axis=1)) |
                        (bars["low"] > bars[["open", "close", "high"]].min(axis=1))).sum())
        volume_bad = int(((bars["quote_volume"] < 0) | (bars["taker_buy_quote"] < 0) |
                          (bars["taker_buy_quote"] > bars["quote_volume"] + 1e-9)).sum())
        funding_bad = int(funding.isna().any(axis=1).sum())
        maximum_gap_hours = float(funding.index.to_series().diff().dt.total_seconds().max() / 3600.0)
        passed = len(bars) == expected_rows and missing == 0 and extras == 0 and ohlc_bad == 0 and volume_bad == 0 and funding_bad == 0 and maximum_gap_hours <= 12.01
        overall = overall and passed
        symbols[symbol] = {
            "bars": len(bars), "expected_bars": expected_rows, "missing_minutes": missing, "extra_minutes": extras,
            "ohlc_bad": ohlc_bad, "volume_bad": volume_bad, "funding_rows": len(funding),
            "funding_missing_rate_or_mark": funding_bad, "maximum_funding_gap_hours": maximum_gap_hours, "status": "PASS" if passed else "FAIL",
        }
        del bars, funding
    write_json(HERE / "data_quality.json", {
        "generated_at_utc": utc_now(), "status": "PASS" if overall else "FAIL",
        "manifest_hash_mismatches": manifest_bad, "symbols": symbols,
    })
    print(json.dumps({"status": "PASS" if overall else "FAIL", "symbols": {k: v["bars"] for k, v in symbols.items()}}))
    if not overall:
        raise RuntimeError("data quality gate failed")


def require_stage(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(stage)
    if read_json(HERE / "data_quality.json")["status"] != "PASS":
        raise RuntimeError("data quality is not PASS")
    prior = {"evaluation": "development", "confirmation": "evaluation"}.get(stage)
    if prior:
        gate_path = HERE / f"{prior}_gate.json"
        if not gate_path.exists() or read_json(gate_path)["status"] != "PASS":
            raise RuntimeError(f"sequential gate blocks {stage}")


def signal_schedule(bars: pd.DataFrame, minute: int) -> pd.DataFrame:
    selected = bars[(bars.index.minute == minute) & bars.index.hour.isin(CONFIG["signal_hours"])].copy()
    selected["oi"] = np.where(
        selected["quote_volume"] > 0,
        2.0 * selected["taker_buy_quote"] / selected["quote_volume"] - 1.0,
        np.nan,
    )
    return selected


def build_trades(symbol: str, bars: pd.DataFrame, funding: pd.DataFrame, stage: str, variant: str) -> pd.DataFrame:
    start, end = STAGES[stage]
    minute = CONFIG["placebo_minute"] if variant == "placebo" else CONFIG["signal_minute"]
    schedule = signal_schedule(bars, minute)
    rows: list[dict] = []
    window = int(CONFIG["rolling_observations"])
    history: list[float] = []
    for signal_time, signal_bar in schedule.iterrows():
        oi = float(signal_bar["oi"])
        if signal_time >= end:
            break
        if signal_time < start:
            if math.isfinite(oi):
                history.append(oi)
            continue
        if len(history) < window or not math.isfinite(oi):
            if math.isfinite(oi):
                history.append(oi)
            continue
        trailing = np.asarray(history[-window:], dtype=float)
        lower = float(np.quantile(trailing, CONFIG["lower_quantile"]))
        upper = float(np.quantile(trailing, CONFIG["upper_quantile"]))
        direction = 1 if oi >= upper else (-1 if oi <= lower else 0)
        history.append(oi)
        if direction == 0:
            continue
        if variant == "momentum":
            prior_time = signal_time - pd.Timedelta(hours=6)
            if prior_time not in bars.index or float(bars.at[prior_time, "close"]) <= 0:
                continue
            six_hour_return = float(signal_bar["close"] / bars.at[prior_time, "close"] - 1.0)
            direction = 1 if six_hour_return >= 0 else -1
        else:
            prior_time = signal_time - pd.Timedelta(hours=6)
            six_hour_return = float(signal_bar["close"] / bars.at[prior_time, "close"] - 1.0) if prior_time in bars.index else float("nan")
        entry_delay = 6 if variant == "delayed5" else 1
        entry = signal_time + pd.Timedelta(minutes=entry_delay)
        exit_time = entry + pd.Timedelta(hours=CONFIG["hold_hours"])
        if exit_time > end or entry not in bars.index or exit_time not in bars.index:
            continue
        entry_price = float(bars.at[entry, "open"])
        exit_price = float(bars.at[exit_time, "open"])
        quantity = float(CONFIG["notional_fraction"]) / entry_price
        held = bars[(bars.index >= entry) & (bars.index < exit_time)]
        if direction > 0:
            maximum_adverse = float(CONFIG["notional_fraction"]) * (float(held["low"].min()) / entry_price - 1.0)
        else:
            maximum_adverse = float(CONFIG["notional_fraction"]) * (1.0 - float(held["high"].max()) / entry_price)
        rates = funding[(funding.index > entry) & (funding.index <= exit_time)]
        actual_funding = float((-direction * quantity * rates["markPrice"] * rates["fundingRate"]).sum())
        stress_funding = actual_funding * (0.5 if actual_funding >= 0 else 1.5)
        slot = "A" if signal_time.hour == 0 else "B"
        rows.append({
            "trade_id": f"{stage}-{variant}-{signal_time.strftime('%Y%m%d%H%M')}-{symbol}",
            "slot_id": f"{signal_time.strftime('%Y%m%d')}-{slot}", "variant": variant, "symbol": symbol,
            "signal_time": signal_time, "decision_time": signal_time + pd.Timedelta(minutes=1),
            "entry_time": entry, "exit_time": exit_time, "oi": oi, "rolling_q25": lower, "rolling_q75": upper,
            "direction": direction, "direction_name": "LONG" if direction > 0 else "SHORT",
            "six_hour_return": six_hour_return, "entry_price": entry_price, "exit_price": exit_price,
            "quantity_per_unit_plan_capital": quantity, "notional_fraction": CONFIG["notional_fraction"],
            "funding_events": int(len(rates)), "actual_funding_return": actual_funding,
            "stress_funding_return": stress_funding, "maximum_adverse_price_return": maximum_adverse,
            "gross_return": direction * quantity * (exit_price - entry_price),
        })
    return pd.DataFrame(rows)


def vectorbt_returns(trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    columns = trades["trade_id"].tolist()
    prices = pd.DataFrame(
        [trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)],
        index=pd.Index([0, 1], name="step"), columns=columns,
    )
    quantity = trades["quantity_per_unit_plan_capital"].to_numpy(float)
    direction = trades["direction"].to_numpy(float)
    sizes = pd.DataFrame([direction * quantity, -direction * quantity], index=prices.index, columns=columns)
    portfolio = vbt.Portfolio.from_orders(
        prices, size=sizes, size_type="amount", direction="both", fees=fee, slippage=slippage,
        init_cash=1.0, freq="1min",
    )
    return portfolio.total_return().reindex(columns).to_numpy(float)


def manual_return(row: pd.Series, fee: float, slippage: float) -> float:
    direction = float(row["direction"])
    quantity = float(row["quantity_per_unit_plan_capital"])
    entry_execution = float(row["entry_price"]) * (1.0 + direction * slippage)
    exit_execution = float(row["exit_price"]) * (1.0 - direction * slippage)
    return direction * quantity * (exit_execution - entry_execution) - fee * quantity * (entry_execution + exit_execution)


def attach_returns(trades: pd.DataFrame) -> pd.DataFrame:
    output = trades.copy()
    if output.empty:
        return output
    for scenario, assumptions in CONFIG["costs"].items():
        vectorized = vectorbt_returns(output, assumptions["fee_per_side"], assumptions["slippage_per_side"])
        manual = output.apply(
            manual_return, axis=1, fee=assumptions["fee_per_side"], slippage=assumptions["slippage_per_side"],
        ).to_numpy(float)
        output[f"{scenario}_price_cost_return"] = vectorized
        output[f"{scenario}_reconciliation_error"] = vectorized - manual
        funding_column = "stress_funding_return" if assumptions["funding_stress"] else "actual_funding_return"
        output[f"{scenario}_net_return"] = vectorized + output[funding_column].to_numpy(float)
    return output


def slot_returns(trades: pd.DataFrame, column: str) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    return (trades.groupby("slot_id")[column].sum() / len(SYMBOLS)).sort_index()


def total_return(values: pd.Series) -> float:
    return float(np.prod(1.0 + values.to_numpy(float)) - 1.0) if len(values) else 0.0


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    equity = (1.0 + values).cumprod()
    return float((equity / equity.cummax() - 1.0).min())


def block_bootstrap_mean_ci(values: np.ndarray, block: int = 16, reps: int = 5000, seed: int = 20260722) -> list[float]:
    values = np.asarray(values, dtype=float)
    if not len(values):
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    means = np.empty(reps)
    for index in range(reps):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(block)) % len(values)).tolist())
        means[index] = values[np.asarray(chosen[: len(values)])].mean()
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def aligned_difference(left: pd.Series, right: pd.Series) -> pd.Series:
    index = left.index.union(right.index)
    return left.reindex(index, fill_value=0.0) - right.reindex(index, fill_value=0.0)


def hurdle_adjust(total: float, start: pd.Timestamp, end: pd.Timestamp) -> float:
    years = (end - start).total_seconds() / (365.0 * 86400.0)
    return float((1.0 + total) / ((1.0 + CONFIG["annual_capital_hurdle"]) ** years) - 1.0)


def summarize_variant(trades: pd.DataFrame, stage: str) -> dict:
    start, end = STAGES[stage]
    maximum_error = max(
        float(trades[f"{scenario}_reconciliation_error"].abs().max()) for scenario in CONFIG["costs"]
    ) if len(trades) else float("nan")
    scenarios: dict[str, dict] = {}
    for scenario in CONFIG["costs"]:
        slots = slot_returns(trades, f"{scenario}_net_return")
        total = total_return(slots)
        scenarios[scenario] = {
            "total_return": total,
            "annualized_return": float((1.0 + total) ** (365.0 * 86400.0 / (end - start).total_seconds()) - 1.0),
            "slot_max_drawdown": max_drawdown(slots),
            "slot_mean_bootstrap_95pct": block_bootstrap_mean_ci(slots.to_numpy(float)),
            "return_after_4pct_annual_hurdle": hurdle_adjust(total, start, end),
            "arithmetic_sum": float(slots.sum()),
        }
    by_symbol = {
        symbol: total_return(group["base_net_return"].sort_index())
        for symbol, group in trades.groupby("symbol")
    }
    base_slots = slot_returns(trades, "base_net_return")
    months_positive: dict[str, float] = {}
    if len(base_slots):
        month_keys = pd.Index([slot[:6] for slot in base_slots.index])
        for month in sorted(set(month_keys)):
            months_positive[f"{month[:4]}-{month[4:]}"] = total_return(base_slots[month_keys == month])
    positive_contributions = {symbol: value for symbol, value in by_symbol.items() if value > 0}
    positive_sum = sum(positive_contributions.values())
    concentration = max(positive_contributions.values()) / positive_sum if positive_sum > 0 else 1.0
    return {
        "trades": int(len(trades)), "funding_events": int(trades["funding_events"].sum()) if len(trades) else 0,
        "longs": int((trades["direction"] > 0).sum()) if len(trades) else 0,
        "shorts": int((trades["direction"] < 0).sum()) if len(trades) else 0,
        "maximum_vectorbt_reconciliation_error": maximum_error,
        "maximum_adverse_price_return": float(trades["maximum_adverse_price_return"].min()) if len(trades) else float("nan"),
        "by_symbol_base": by_symbol, "by_month_base": months_positive,
        "positive_symbol_count": sum(value > 0 for value in by_symbol.values()),
        "positive_month_count": sum(value > 0 for value in months_positive.values()),
        "largest_positive_symbol_share": float(concentration), "scenarios": scenarios,
        "gross_slot_mean_bootstrap_95pct": block_bootstrap_mean_ci(slot_returns(trades, "gross_return").to_numpy(float)),
        "gross_slot_mean": float(slot_returns(trades, "gross_return").mean()) if len(trades) else float("nan"),
    }


def analyze(stage: str) -> None:
    verify_checkpoint()
    require_stage(stage)
    variants = ["main", "delayed5", "placebo", "momentum"]
    pieces: dict[str, list[pd.DataFrame]] = {variant: [] for variant in variants}
    for symbol in SYMBOLS:
        bars = load_bars(symbol)
        funding = load_funding(symbol)
        for variant in variants:
            pieces[variant].append(build_trades(symbol, bars, funding, stage, variant))
        del bars, funding
    trades = {variant: attach_returns(pd.concat(parts, ignore_index=True)) for variant, parts in pieces.items()}
    summaries = {variant: summarize_variant(frame, stage) for variant, frame in trades.items()}
    main_base = slot_returns(trades["main"], "base_net_return")
    placebo_base = slot_returns(trades["placebo"], "base_net_return")
    momentum_base = slot_returns(trades["momentum"], "base_net_return")
    placebo_diff = aligned_difference(main_base, placebo_base)
    momentum_diff = aligned_difference(main_base, momentum_base)
    payload = {
        "generated_at_utc": utc_now(), "stage": stage, "main": summaries["main"],
        "diagnostics": {key: summaries[key] for key in ["delayed5", "placebo", "momentum"]},
        "incremental": {
            "main_minus_placebo_base_slot_mean": float(placebo_diff.mean()),
            "main_minus_placebo_bootstrap_95pct": block_bootstrap_mean_ci(placebo_diff.to_numpy(float)),
            "main_minus_momentum_base_slot_mean": float(momentum_diff.mean()),
            "main_minus_momentum_bootstrap_95pct": block_bootstrap_mean_ci(momentum_diff.to_numpy(float)),
        },
        "portfolio_interpretation": "six equal capital sleeves; each sleeve uses at most 0.25x, so aggregate maximum simultaneous notional is 0.25x",
    }
    write_json(HERE / f"{stage}.json", payload)
    trades["main"].to_csv(HERE / f"{stage}_trades.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    for variant in ["delayed5", "placebo", "momentum"]:
        trades[variant].to_csv(HERE / f"{stage}_{variant}_trades.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    print(json.dumps({"stage": stage, "trades": summaries["main"]["trades"],
                      "base_total": summaries["main"]["scenarios"]["base"]["total_return"],
                      "gross_mean": summaries["main"]["gross_slot_mean"]}))


def gate(stage: str) -> None:
    require_stage(stage)
    result = read_json(HERE / f"{stage}.json")
    main = result["main"]
    minimum = {"development": 500, "evaluation": 350, "confirmation": 300}[stage]
    positive_month_requirement = math.floor(len(main["by_month_base"]) / 2) + 1
    confirmation = stage == "confirmation"
    checks = {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "vectorbt_reconciled": main["maximum_vectorbt_reconciliation_error"] <= 1e-12,
        "minimum_trades": main["trades"] >= minimum,
        "favorable_total_positive": main["scenarios"]["favorable"]["total_return"] > 0,
        "base_total_positive": main["scenarios"]["base"]["total_return"] > 0,
        "stress_total_positive": main["scenarios"]["stress"]["total_return"] > 0,
        "stress_after_hurdle_positive": main["scenarios"]["stress"]["return_after_4pct_annual_hurdle"] > 0,
        "gross_mean_positive": main["gross_slot_mean"] > 0,
        "gross_bootstrap_lower_positive": confirmation or main["gross_slot_mean_bootstrap_95pct"][0] > 0,
        "main_minus_placebo_mean_positive": result["incremental"]["main_minus_placebo_base_slot_mean"] > 0,
        "main_minus_placebo_bootstrap_lower_positive": confirmation or result["incremental"]["main_minus_placebo_bootstrap_95pct"][0] > 0,
        "main_minus_momentum_mean_positive": result["incremental"]["main_minus_momentum_base_slot_mean"] > 0,
        "main_minus_momentum_bootstrap_lower_positive": confirmation or result["incremental"]["main_minus_momentum_bootstrap_95pct"][0] > 0,
        "delayed5_stress_positive": result["diagnostics"]["delayed5"]["scenarios"]["stress"]["total_return"] > 0,
        "at_least_four_symbols_positive": main["positive_symbol_count"] >= 4,
        "positive_months_over_half": main["positive_month_count"] >= positive_month_requirement,
        "slot_drawdown_within_limit": main["scenarios"]["base"]["slot_max_drawdown"] > (-0.12 if confirmation else -0.15),
        "single_plan_adverse_within_limit": main["maximum_adverse_price_return"] > (-0.12 if confirmation else -0.15),
        "largest_positive_symbol_share_at_most_half": main["largest_positive_symbol_share"] <= 0.5,
    }
    failed = [name for name, passed in checks.items() if not passed]
    status = "PASS" if not failed else "FAIL"
    write_json(HERE / f"{stage}_gate.json", {
        "generated_at_utc": utc_now(), "stage": stage, "status": status, "checks": checks,
        "failed_checks": failed, "result_digest": result["content_digest"],
    })
    if stage == "development" and status == "FAIL":
        if (main["scenarios"]["favorable"]["total_return"] <= 0 or main["scenarios"]["base"]["total_return"] <= 0
                or main["scenarios"]["stress"]["total_return"] <= 0 or main["gross_slot_mean"] <= 0):
            conclusion = "DOES_NOT_SUPPORT"
        else:
            conclusion = "INSUFFICIENT_EVIDENCE"
        write_json(HERE / "results.json", {
            "generated_at_utc": utc_now(), "conclusion": conclusion, "stopped_after": "development",
            "gate_status": status, "failed_checks": failed, "main": main,
            "diagnostics": result["diagnostics"], "incremental": result["incremental"],
            "later_stages": "NOT_OPENED_BY_SEQUENTIAL_GATE", "handoff": "NOT_GENERATED", "product_effects": "NONE",
        })
    print(json.dumps({"stage": stage, "status": status, "failed": failed}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["checkpoint", "fetch", "inspect", "analyze", "gate"])
    parser.add_argument("--stage", choices=list(STAGES), default="development")
    args = parser.parse_args()
    if args.command == "checkpoint":
        checkpoint()
    elif args.command == "fetch":
        fetch()
    elif args.command == "inspect":
        inspect()
    elif args.command == "analyze":
        analyze(args.stage)
    elif args.command == "gate":
        gate(args.stage)


if __name__ == "__main__":
    main()
