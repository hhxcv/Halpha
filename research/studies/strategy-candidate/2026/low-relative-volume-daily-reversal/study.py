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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[5]
CACHE_ROOT = Path(
    os.environ.get(
        "HALPHA_REVERSAL_CACHE",
        "D:/projects/Codex/CodexHome/research-data/halpha/low-relative-volume-daily-reversal/2026-07-22-v1",
    )
)

BASE_URL = "https://fapi.binance.com"
SYMBOLS = ["ALGOUSDT", "COMPUSDT", "THETAUSDT", "VETUSDT", "XTZUSDT", "ZECUSDT"]
DATA_START = "2020-11-01T00:00:00Z"
DATA_END = "2025-07-01T00:00:00Z"
STAGES = {
    "development": ("2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2025-07-01T00:00:00Z"),
}
CONFIG = {
    "strategy_id": "RESEARCH_LOW_RELATIVE_VOLUME_DAILY_REVERSAL_30D_1P5Z_V1",
    "return_vol_window_days": 30,
    "volume_window_days": 30,
    "return_z_threshold": 1.5,
    "volume_shock_max": 0.0,
    "min_median_quote_volume_30d": 5_000_000.0,
    "hold_hours": 24,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020},
    },
    "diagnostics": [
        "unconditional_extreme_reversal",
        "low_volume_extreme_momentum",
        "volume_window_60d",
    ],
}


def utc_ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1000)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_digest(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def request_json(endpoint: str, params: dict[str, Any]) -> tuple[bytes, str]:
    url = f"{BASE_URL}{endpoint}?{urllib.parse.urlencode(params)}"
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Halpha-Research/1.0"})
            with urllib.request.urlopen(req, timeout=90) as response:
                raw = response.read()
            json.loads(raw)
            return raw, url
        except Exception as exc:  # retrieval-only retry; every exhausted failure remains visible to the caller
            last_error = exc
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def checkpoint() -> None:
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {"id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1"},
        "research_kind": "STRATEGY_CANDIDATE",
        "question": "Does a fixed one-day extreme-return reversal conditioned on low relative volume survive realistic costs and funding in long-lived Binance USD-M perps?",
        "symbols": SYMBOLS,
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END,
        "stages": STAGES,
        "config": CONFIG,
        "stage_open_rule": "development first; evaluation only after development_gate PASS; confirmation only after evaluation_gate PASS",
        "allowed_fixes": "retrieval, parsing, completeness, deterministic statistics, or implementation bugs that do not change the economic rule; record every outcome-affecting fix",
        "study_py_sha256": sha256_file(Path(__file__)),
        "readme_sha256": sha256_file(HERE / "README.md"),
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
    cp = read_json(path)
    if cp["symbols"] != SYMBOLS or cp["config"] != CONFIG or cp["stages"] != {k: list(v) if isinstance(v, tuple) else v for k, v in STAGES.items()}:
        # JSON turns tuples into lists; normalize both sides.
        normalized = json.loads(json.dumps(STAGES))
        if cp["symbols"] != SYMBOLS or cp["config"] != CONFIG or cp["stages"] != normalized:
            raise RuntimeError("checkpoint no longer matches fixed configuration")
    return cp


def fetch_pages(endpoint: str, base_params: dict[str, Any], time_key: str, limit: int, out_dir: Path) -> list[dict[str, Any]]:
    start = utc_ms(DATA_START)
    end = utc_ms(DATA_END)
    pages: list[dict[str, Any]] = []
    page_no = 0
    while start < end:
        params = dict(base_params)
        params.update({"startTime": start, "endTime": end - 1, "limit": limit})
        raw, url = request_json(endpoint, params)
        rows = json.loads(raw)
        if not rows:
            break
        page_path = out_dir / f"{time_key}-{page_no:03d}.json"
        if page_path.exists():
            existing = page_path.read_bytes()
            if existing != raw:
                raise RuntimeError(f"refusing to overwrite different raw page: {page_path}")
        else:
            page_path.parent.mkdir(parents=True, exist_ok=True)
            page_path.write_bytes(raw)
        pages.append(
            {
                "url": url,
                "path": str(page_path),
                "bytes": len(raw),
                "sha256": sha256_bytes(raw),
                "rows": len(rows),
                "first_time_ms": int(rows[0][0] if isinstance(rows[0], list) else rows[0][time_key]),
                "last_time_ms": int(rows[-1][0] if isinstance(rows[-1], list) else rows[-1][time_key]),
            }
        )
        last = int(rows[-1][0] if isinstance(rows[-1], list) else rows[-1][time_key])
        next_start = last + 1
        if next_start <= start:
            raise RuntimeError(f"non-advancing pagination for {endpoint}")
        start = next_start
        page_no += 1
        time.sleep(0.08)
    return pages


def fetch() -> None:
    cp = ensure_checkpoint()
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "accessed_at_utc": iso_now(),
        "checkpoint_digest": cp["content_digest"],
        "source": "Binance public USD-M REST market data; no credentials",
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END,
        "symbols": {},
    }
    for symbol in SYMBOLS:
        symbol_dir = CACHE_ROOT / symbol / "raw"
        kline_pages = fetch_pages(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": "1d"},
            "openTime",
            1500,
            symbol_dir / "klines",
        )
        funding_pages = fetch_pages(
            "/fapi/v1/fundingRate",
            {"symbol": symbol},
            "fundingTime",
            1000,
            symbol_dir / "funding",
        )
        manifest["symbols"][symbol] = {"kline_pages": kline_pages, "funding_pages": funding_pages}
        print(json.dumps({"symbol": symbol, "kline_pages": len(kline_pages), "funding_pages": len(funding_pages)}))
    manifest["content_digest"] = canonical_digest(manifest)
    write_json(HERE / "source_manifest.json", manifest)
    print(json.dumps({"manifest": str(HERE / "source_manifest.json"), "digest": manifest["content_digest"]}))


def load_rows(page_items: list[dict[str, Any]]) -> list[Any]:
    rows: list[Any] = []
    for item in page_items:
        path = Path(item["path"])
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or sha256_bytes(raw) != item["sha256"]:
            raise RuntimeError(f"source identity mismatch: {path}")
        rows.extend(json.loads(raw))
    return rows


@dataclass
class SymbolData:
    bars: pd.DataFrame
    funding: pd.DataFrame


def load_symbol(symbol: str) -> SymbolData:
    manifest = read_json(HERE / "source_manifest.json")
    item = manifest["symbols"][symbol]
    krows = load_rows(item["kline_pages"])
    bars = pd.DataFrame(
        krows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "trade_count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
        ],
    )
    bars["open_time"] = pd.to_datetime(bars["open_time"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="raise")
    bars = bars.drop_duplicates("open_time", keep="last").sort_values("open_time").set_index("open_time")

    frows = load_rows(item["funding_pages"])
    funding = pd.DataFrame(frows)
    if funding.empty:
        funding = pd.DataFrame(columns=["fundingTime", "fundingRate"])
    funding["fundingTime"] = pd.to_datetime(funding["fundingTime"], unit="ms", utc=True)
    funding["fundingRate"] = pd.to_numeric(funding["fundingRate"], errors="raise")
    funding = funding.drop_duplicates("fundingTime", keep="last").sort_values("fundingTime").set_index("fundingTime")
    return SymbolData(bars=bars, funding=funding)


def inspect() -> None:
    ensure_checkpoint()
    if not (HERE / "source_manifest.json").exists():
        raise RuntimeError("source_manifest.json missing; run fetch")
    out: dict[str, Any] = {"checked_at_utc": iso_now(), "symbols": {}, "overall": "PASS"}
    expected_start = pd.Timestamp(DATA_START)
    expected_end = pd.Timestamp(DATA_END)
    for symbol in SYMBOLS:
        data = load_symbol(symbol)
        bars = data.bars[(data.bars.index >= expected_start) & (data.bars.index < expected_end)]
        expected_index = pd.date_range(expected_start, expected_end, freq="1D", inclusive="left")
        missing = expected_index.difference(bars.index)
        invalid_ohlc = int(((bars[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
        invalid_range = int(((bars["high"] < bars[["open", "close"]].max(axis=1)) | (bars["low"] > bars[["open", "close"]].min(axis=1))).sum())
        funding = data.funding[(data.funding.index >= expected_start) & (data.funding.index < expected_end)]
        status = "PASS" if len(missing) == 0 and invalid_ohlc == 0 and invalid_range == 0 and len(funding) > 1000 else "FAIL"
        if status != "PASS":
            out["overall"] = "FAIL"
        out["symbols"][symbol] = {
            "status": status,
            "bar_rows": int(len(bars)),
            "bar_first": bars.index.min().isoformat() if len(bars) else None,
            "bar_last": bars.index.max().isoformat() if len(bars) else None,
            "missing_daily_bars": int(len(missing)),
            "missing_first_10": [x.isoformat() for x in missing[:10]],
            "invalid_ohlc": invalid_ohlc,
            "invalid_range": invalid_range,
            "funding_rows": int(len(funding)),
            "funding_first": funding.index.min().isoformat() if len(funding) else None,
            "funding_last": funding.index.max().isoformat() if len(funding) else None,
            "median_quote_volume": float(bars["quote_volume"].median()) if len(bars) else None,
        }
    out["source_manifest_sha256"] = sha256_file(HERE / "source_manifest.json")
    out["content_digest"] = canonical_digest(out)
    write_json(HERE / "data_quality.json", out)
    print(json.dumps({"overall": out["overall"], "digest": out["content_digest"]}))
    if out["overall"] != "PASS":
        raise RuntimeError("data quality failed")


def add_features(bars: pd.DataFrame, volume_window: int, use_volume_filter: bool, momentum: bool) -> pd.DataFrame:
    out = bars.copy()
    ret = out["close"].pct_change()
    prior_std = ret.shift(1).rolling(CONFIG["return_vol_window_days"], min_periods=CONFIG["return_vol_window_days"]).std(ddof=1)
    prior_qv_mean = out["quote_volume"].shift(1).rolling(volume_window, min_periods=volume_window).mean()
    prior_log_qv_std = np.log(out["quote_volume"]).shift(1).rolling(volume_window, min_periods=volume_window).std(ddof=1)
    prior_qv_median = out["quote_volume"].shift(1).rolling(30, min_periods=30).median()
    out["return"] = ret
    out["return_z"] = ret / prior_std
    out["volume_shock"] = (np.log(out["quote_volume"]) - np.log(prior_qv_mean)) / prior_log_qv_std
    out["market_quality"] = prior_qv_median >= CONFIG["min_median_quote_volume_30d"]
    direction = pd.Series(0, index=out.index, dtype=int)
    direction[out["return_z"] <= -CONFIG["return_z_threshold"]] = 1
    direction[out["return_z"] >= CONFIG["return_z_threshold"]] = -1
    if momentum:
        direction *= -1
    if use_volume_filter:
        direction[out["volume_shock"] > CONFIG["volume_shock_max"]] = 0
    direction[~out["market_quality"]] = 0
    direction[~np.isfinite(out["return_z"]) | ~np.isfinite(out["volume_shock"])] = 0
    out["direction"] = direction
    return out


def build_trades(symbol: str, data: SymbolData, stage: str, volume_window: int = 30, use_volume_filter: bool = True, momentum: bool = False) -> pd.DataFrame:
    featured = add_features(data.bars, volume_window, use_volume_filter, momentum)
    start, end = map(pd.Timestamp, STAGES[stage])
    rows: list[dict[str, Any]] = []
    for signal_time, row in featured[featured["direction"] != 0].iterrows():
        entry_time = signal_time + pd.Timedelta(days=1)
        exit_time = signal_time + pd.Timedelta(days=2)
        if entry_time < start or entry_time >= end:
            continue
        if entry_time not in featured.index or exit_time not in featured.index:
            continue
        direction = int(row["direction"])
        entry_price = float(featured.at[entry_time, "open"])
        exit_price = float(featured.at[exit_time, "open"])
        rates = data.funding[(data.funding.index > entry_time) & (data.funding.index < exit_time)]["fundingRate"]
        rows.append(
            {
                "trade_id": f"{symbol}-{entry_time.strftime('%Y%m%d')}-{direction:+d}",
                "symbol": symbol,
                "signal_time": signal_time,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "funding_rate_sum": float(rates.sum()),
                "funding_events": int(len(rates)),
                "funding_return": float(-direction * rates.sum()),
                "return_z": float(row["return_z"]),
                "volume_shock": float(row["volume_shock"]),
                "quote_volume": float(row["quote_volume"]),
            }
        )
    return pd.DataFrame(rows)


def vectorbt_trade_returns(trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    if trades.empty:
        return np.array([], dtype=float)
    cols = trades["trade_id"].tolist()
    prices = pd.DataFrame(
        [trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)],
        index=pd.Index([0, 1], name="step"),
        columns=cols,
    )
    entries = pd.DataFrame(False, index=prices.index, columns=cols)
    exits = entries.copy()
    short_entries = entries.copy()
    short_exits = entries.copy()
    long_cols = trades.loc[trades["direction"] == 1, "trade_id"].tolist()
    short_cols = trades.loc[trades["direction"] == -1, "trade_id"].tolist()
    if long_cols:
        entries.loc[0, long_cols] = True
        exits.loc[1, long_cols] = True
    if short_cols:
        short_entries.loc[0, short_cols] = True
        short_exits.loc[1, short_cols] = True
    pf = vbt.Portfolio.from_signals(
        prices,
        entries=entries,
        exits=exits,
        short_entries=short_entries,
        short_exits=short_exits,
        fees=fee,
        slippage=slippage,
        init_cash=1.0,
        size=np.inf,
        freq="1D",
    )
    return pf.total_return().reindex(cols).to_numpy(float)


def attach_returns(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    if out.empty:
        return out
    for name, costs in CONFIG["costs"].items():
        price_cost_return = vectorbt_trade_returns(out, costs["fee_per_side"], costs["slippage_per_side"])
        out[f"{name}_price_cost_return"] = price_cost_return
        out[f"{name}_net_return"] = price_cost_return + out["funding_return"].to_numpy(float)
    return out


def daily_portfolio_returns(trades: pd.DataFrame, column: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    idx = pd.date_range(start, end, freq="1D", inclusive="left")
    if trades.empty:
        return pd.Series(0.0, index=idx)
    by_day = trades.groupby("entry_time")[column].mean()
    return by_day.reindex(idx, fill_value=0.0).astype(float)


def block_bootstrap_mean_ci(values: np.ndarray, block: int = 30, reps: int = 5000, seed: int = 20260722) -> list[float]:
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return [math.nan, math.nan]
    rng = np.random.default_rng(seed)
    starts = np.arange(n)
    means = np.empty(reps, dtype=float)
    for i in range(reps):
        chosen: list[int] = []
        while len(chosen) < n:
            s = int(rng.choice(starts))
            chosen.extend(((s + np.arange(block)) % n).tolist())
        means[i] = values[np.asarray(chosen[:n])].mean()
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def summarize(trades: pd.DataFrame, stage: str, label: str) -> dict[str, Any]:
    start, end = map(pd.Timestamp, STAGES[stage])
    result: dict[str, Any] = {"label": label, "trades": int(len(trades))}
    if trades.empty:
        return result
    result["long_trades"] = int((trades["direction"] == 1).sum())
    result["short_trades"] = int((trades["direction"] == -1).sum())
    result["funding_return_sum"] = float(trades["funding_return"].sum())
    result["funding_events"] = int(trades["funding_events"].sum())
    result["by_symbol"] = {}
    result["by_year"] = {}
    for scenario in CONFIG["costs"]:
        col = f"{scenario}_net_return"
        daily = daily_portfolio_returns(trades, col, start, end)
        equity = (1.0 + daily).cumprod()
        drawdown = equity / equity.cummax() - 1.0
        accessor = daily.vbt.returns(freq="1D")
        result[scenario] = {
            "mean_trade_return": float(trades[col].mean()),
            "median_trade_return": float(trades[col].median()),
            "win_rate": float((trades[col] > 0).mean()),
            "total_return": float(equity.iloc[-1] - 1.0),
            "max_drawdown": float(drawdown.min()),
            "annualized_sharpe": float(accessor.sharpe_ratio()) if daily.std(ddof=1) > 0 else 0.0,
            "daily_mean": float(daily.mean()),
            "daily_block_bootstrap_mean_ci95": block_bootstrap_mean_ci(daily.to_numpy()),
        }
        for symbol, part in trades.groupby("symbol"):
            sym_returns = daily_portfolio_returns(part, col, start, end)
            sym_total = float((1.0 + sym_returns).prod() - 1.0)
            result["by_symbol"].setdefault(symbol, {})[scenario] = sym_total
        for year, part in daily.groupby(daily.index.year):
            result["by_year"].setdefault(str(year), {})[scenario] = float((1.0 + part).prod() - 1.0)
    result["base_positive_symbols"] = int(sum(v["base"] > 0 for v in result["by_symbol"].values()))
    result["signal_return_z_abs_median"] = float(trades["return_z"].abs().median())
    result["signal_volume_shock_median"] = float(trades["volume_shock"].median())
    return result


def stage_allowed(stage: str) -> bool:
    if stage == "development":
        return True
    prior = "development" if stage == "evaluation" else "evaluation"
    path = HERE / f"{prior}_gate.json"
    return path.exists() and read_json(path).get("status") == "PASS"


def analyze(stage: str) -> None:
    ensure_checkpoint()
    dq = read_json(HERE / "data_quality.json")
    if dq["overall"] != "PASS":
        raise RuntimeError("data quality not PASS")
    if not stage_allowed(stage):
        raise RuntimeError(f"{stage} is sealed: prior gate is not PASS")
    configs = {
        "main_30d_low_volume_reversal": dict(volume_window=30, use_volume_filter=True, momentum=False),
        "unconditional_extreme_reversal": dict(volume_window=30, use_volume_filter=False, momentum=False),
        "low_volume_extreme_momentum": dict(volume_window=30, use_volume_filter=True, momentum=True),
        "sensitivity_60d_low_volume_reversal": dict(volume_window=60, use_volume_filter=True, momentum=False),
    }
    output: dict[str, Any] = {
        "generated_at_utc": iso_now(),
        "stage": stage,
        "stage_interval": STAGES[stage],
        "checkpoint_digest": read_json(HERE / "checkpoint.json")["content_digest"],
        "source_manifest_sha256": sha256_file(HERE / "source_manifest.json"),
        "config_results": {},
        "full_configuration_count": len(configs),
        "selection_rule": "main configuration only; diagnostics cannot replace it",
    }
    trade_tables: dict[str, pd.DataFrame] = {}
    loaded = {symbol: load_symbol(symbol) for symbol in SYMBOLS}
    for label, kwargs in configs.items():
        parts = [build_trades(symbol, loaded[symbol], stage, **kwargs) for symbol in SYMBOLS]
        trades = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        trades = attach_returns(trades)
        trade_tables[label] = trades
        output["config_results"][label] = summarize(trades, stage, label)
    main = output["config_results"]["main_30d_low_volume_reversal"]
    unconditional = output["config_results"]["unconditional_extreme_reversal"]
    output["main_vs_unconditional_base_daily_mean_delta"] = (
        main.get("base", {}).get("daily_mean", math.nan) - unconditional.get("base", {}).get("daily_mean", math.nan)
    )
    output["content_digest"] = canonical_digest(output)
    write_json(HERE / f"{stage}.json", output)
    main_trades = trade_tables["main_30d_low_volume_reversal"].copy()
    if not main_trades.empty:
        for col in ["signal_time", "entry_time", "exit_time"]:
            main_trades[col] = main_trades[col].map(lambda x: x.isoformat())
        main_trades.to_csv(HERE / f"{stage}_trades.csv", index=False, float_format="%.12g")
    print(json.dumps({"stage": stage, "main_trades": main.get("trades", 0), "digest": output["content_digest"]}))


def gate(stage: str) -> None:
    result = read_json(HERE / f"{stage}.json")
    main = result["config_results"]["main_30d_low_volume_reversal"]
    reasons: list[str] = []
    if stage == "development":
        checks = {
            "trades_at_least_120": main.get("trades", 0) >= 120,
            "base_total_positive": main.get("base", {}).get("total_return", -1.0) > 0,
            "stress_total_positive": main.get("stress", {}).get("total_return", -1.0) > 0,
            "base_bootstrap_lower_positive": main.get("base", {}).get("daily_block_bootstrap_mean_ci95", [-1.0])[0] > 0,
            "base_positive_symbols_at_least_4": main.get("base_positive_symbols", 0) >= 4,
            "volume_filter_improves_base_daily_mean": result.get("main_vs_unconditional_base_daily_mean_delta", -1.0) > 0,
        }
    elif stage == "evaluation":
        checks = {
            "trades_at_least_120": main.get("trades", 0) >= 120,
            "base_total_positive": main.get("base", {}).get("total_return", -1.0) > 0,
            "stress_total_positive": main.get("stress", {}).get("total_return", -1.0) > 0,
            "base_2023_positive": main.get("by_year", {}).get("2023", {}).get("base", -1.0) > 0,
            "base_2024_positive": main.get("by_year", {}).get("2024", {}).get("base", -1.0) > 0,
            "base_bootstrap_lower_positive": main.get("base", {}).get("daily_block_bootstrap_mean_ci95", [-1.0])[0] > 0,
            "base_positive_symbols_at_least_4": main.get("base_positive_symbols", 0) >= 4,
        }
    else:
        checks = {
            "trades_at_least_30": main.get("trades", 0) >= 30,
            "base_total_positive": main.get("base", {}).get("total_return", -1.0) > 0,
            "stress_total_positive": main.get("stress", {}).get("total_return", -1.0) > 0,
            "base_positive_symbols_at_least_3": main.get("base_positive_symbols", 0) >= 3,
            "base_max_drawdown_above_minus_15pct": main.get("base", {}).get("max_drawdown", -1.0) >= -0.15,
            "base_daily_mean_positive": main.get("base", {}).get("daily_mean", -1.0) > 0,
        }
    for name, passed in checks.items():
        if not passed:
            reasons.append(name)
    out = {
        "generated_at_utc": iso_now(),
        "stage": stage,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failed_checks": reasons,
        "result_digest": result["content_digest"],
    }
    out["content_digest"] = canonical_digest(out)
    write_json(HERE / f"{stage}_gate.json", out)
    print(json.dumps(out))


def combine() -> None:
    stages_present = [stage for stage in STAGES if (HERE / f"{stage}.json").exists()]
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in stages_present if (HERE / f"{stage}_gate.json").exists()}
    if not stages_present:
        raise RuntimeError("no stage results")
    if "development" not in gates:
        raise RuntimeError("development gate missing")
    if gates["development"]["status"] != "PASS":
        dev = read_json(HERE / "development.json")["config_results"]["main_30d_low_volume_reversal"]
        economic_fail = dev.get("trades", 0) >= 120 and (
            dev.get("base", {}).get("total_return", -1.0) <= 0
            or dev.get("stress", {}).get("total_return", -1.0) <= 0
            or read_json(HERE / "development.json").get("main_vs_unconditional_base_daily_mean_delta", -1.0) <= 0
        )
        conclusion = "DOES_NOT_SUPPORT" if economic_fail else "INSUFFICIENT_EVIDENCE"
    elif "evaluation" not in gates:
        conclusion = "CANNOT_DETERMINE"
    elif gates["evaluation"]["status"] != "PASS":
        ev = read_json(HERE / "evaluation.json")["config_results"]["main_30d_low_volume_reversal"]
        economic_fail = ev.get("trades", 0) >= 120 and (
            ev.get("base", {}).get("total_return", -1.0) <= 0 or ev.get("stress", {}).get("total_return", -1.0) <= 0
        )
        conclusion = "DOES_NOT_SUPPORT" if economic_fail else "INSUFFICIENT_EVIDENCE"
    elif "confirmation" not in gates:
        conclusion = "CANNOT_DETERMINE"
    elif gates["confirmation"]["status"] == "PASS":
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    else:
        cf = read_json(HERE / "confirmation.json")["config_results"]["main_30d_low_volume_reversal"]
        economic_fail = cf.get("trades", 0) >= 30 and (
            cf.get("base", {}).get("total_return", -1.0) <= 0 or cf.get("stress", {}).get("total_return", -1.0) <= 0
        )
        conclusion = "DOES_NOT_SUPPORT" if economic_fail else "INSUFFICIENT_EVIDENCE"
    out = {
        "generated_at_utc": iso_now(),
        "conclusion": conclusion,
        "stages_present": stages_present,
        "gates": {k: v["status"] for k, v in gates.items()},
        "product_effects": "NONE",
        "external_cache": str(CACHE_ROOT),
        "source_manifest_sha256": sha256_file(HERE / "source_manifest.json"),
        "study_py_sha256": sha256_file(Path(__file__)),
    }
    out["content_digest"] = canonical_digest(out)
    write_json(HERE / "results.json", out)
    print(json.dumps(out))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint")
    sub.add_parser("fetch")
    sub.add_parser("inspect")
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("--stage", required=True, choices=list(STAGES))
    gate_parser = sub.add_parser("gate")
    gate_parser.add_argument("--stage", required=True, choices=list(STAGES))
    sub.add_parser("combine")
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
    elif args.command == "combine":
        combine()


if __name__ == "__main__":
    main()
