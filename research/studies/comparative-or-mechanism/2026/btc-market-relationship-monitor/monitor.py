"""Reproducible BTC relationship research and a standalone local monitor.

Public market-data reads only. This module never imports product code, reads product
configuration, or exposes an exchange-changing operation.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import plotly.offline
import requests
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.multitest import multipletests


QUESTION_DIR = Path(__file__).resolve().parent
RESEARCH_ROOT = next((path for path in QUESTION_DIR.parents if path.name == "research"), None)
if RESEARCH_ROOT is None:
    raise RuntimeError(f"cannot locate research root from {QUESTION_DIR}")
UNIVERSE_PATH = RESEARCH_ROOT / "market-universe" / "universe.csv"
EVIDENCE_DIR = QUESTION_DIR / "evidence"
APP_DIR = QUESTION_DIR / "app"
DEFAULT_CACHE_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/btc-market-relationship-monitor"
)
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
COIN_METRICS_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
COIN_METRICS_FIELD = "PriceUSD"
REFERENCE_SYMBOL = "BTCUSDT"
DAY_MS = 86_400_000
FETCH_DAYS = 800
MAIN_WINDOW = 365
MIN_OBS = 120
SUB_WINDOW = 180
MIN_SUB_OBS = 90
ROLLING_WINDOW = 90
ROLLING_MIN_OBS = 60
HAC_LAGS = 7
FDR_ALPHA = 0.05
STRONG_CORRELATION = 0.50
KNOWN_CRYPTO_SUFFIX_B_EXCEPTIONS = {"DGB"}
ANCHOR_CROSSCHECK = {
    "BTCUSDT": "btc",
    "ETHUSDT": "eth",
    "SOLUSDT": "sol",
    "SUIUSDT": "sui",
    "DOGEUSDT": "doge",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    # Preserve the millisecond cutoff used by Binance klines. Dropping ``.999``
    # would make a valid last closed bar appear to extend beyond the recorded
    # research boundary during independent validation.
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def get_with_retry(url: str, *, params: dict[str, Any], timeout: float, attempts: int = 3) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    assert last_error is not None
    raise last_error


def latest_closed_cutoff(now: datetime | None = None) -> datetime:
    current = (now or utc_now()).astimezone(UTC)
    return current.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(milliseconds=1)


def load_universe(path: Path = UNIVERSE_PATH) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    active = frame[
        (frame["market"] == "BINANCE_SPOT")
        & (frame["currently_trading"].str.lower() == "true")
        & (frame["quote_asset"] == "USDT")
        & frame["economic_exposure"].isin(["CRYPTO_NATIVE", "CRYPTO_ANCHOR"])
    ].copy()
    # Binance introduced bStocks after the recorded universe classifier was built.
    # Spot exchangeInfo has no economic taxonomy, so these were defaulted to
    # CRYPTO_NATIVE. The conjunction below is deliberately narrower than a plain
    # suffix rule and is recorded as a post-reveal semantic correction.
    bstock_mask = (
        active["economic_exposure_source"].eq("DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS")
        & active["classification_subtypes"].eq("")
        & active["base_asset"].str.endswith("B")
        & ~active["base_asset"].isin(KNOWN_CRYPTO_SUFFIX_B_EXCEPTIONS)
    )
    excluded_bstocks = active[bstock_mask].sort_values("symbol")
    active = active[~bstock_mask].copy()
    active = active.drop_duplicates(subset=["symbol"], keep="last").sort_values("symbol")
    if REFERENCE_SYMBOL not in set(active["symbol"]):
        raise ValueError(f"reference {REFERENCE_SYMBOL} is absent from the recorded universe")
    snapshot_values = sorted(set(active["snapshot_time_utc"]))
    if len(snapshot_values) != 1:
        raise ValueError(f"universe has non-unique snapshot times: {snapshot_values}")
    identity = {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "snapshot_time_utc": snapshot_values[0],
        "eligible_including_reference": int(len(active)),
        "eligible_objects": int(len(active) - 1),
        "excluded_bstock_count": int(len(excluded_bstocks)),
        "excluded_bstock_symbols": excluded_bstocks["symbol"].tolist(),
        "bstock_suffix_crypto_exceptions": sorted(KNOWN_CRYPTO_SUFFIX_B_EXCEPTIONS),
        "selection": (
            "BINANCE_SPOT; currently_trading=True; quote_asset=USDT; "
            "economic_exposure in {CRYPTO_NATIVE,CRYPTO_ANCHOR}; conservative bStock semantic exclusion; "
            "BTCUSDT is reference"
        ),
    }
    return active, identity


def normalize_binance_klines(rows: list[list[Any]], cutoff_ms: int) -> tuple[pd.DataFrame, dict[str, int]]:
    columns = [
        "open_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time_ms",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "ignore",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return frame, {"input_rows": 0, "duplicate_rows": 0, "invalid_rows": 0, "open_rows": 0}
    for column in ["open_time_ms", "close_time_ms", "trade_count"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    input_rows = len(frame)
    open_rows = int((frame["close_time_ms"] > cutoff_ms).sum())
    invalid = (
        frame[["open_time_ms", "close_time_ms", "open", "high", "low", "close"]].isna().any(axis=1)
        | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (frame["close_time_ms"] > cutoff_ms)
    )
    invalid_rows = int(invalid.sum())
    frame = frame[~invalid].copy()
    duplicate_rows = int(frame.duplicated(subset=["open_time_ms"], keep="last").sum())
    frame = frame.drop_duplicates(subset=["open_time_ms"], keep="last")
    frame = frame.sort_values("open_time_ms").reset_index(drop=True)
    frame["open_time_utc"] = pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True)
    frame["close_time_utc"] = pd.to_datetime(frame["close_time_ms"], unit="ms", utc=True)
    return frame[columns + ["open_time_utc", "close_time_utc"]], {
        "input_rows": int(input_rows),
        "duplicate_rows": duplicate_rows,
        "invalid_rows": invalid_rows,
        "open_rows": open_rows,
    }


def _read_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    if frame.empty:
        return frame
    frame["open_time_ms"] = pd.to_numeric(frame["open_time_ms"], errors="coerce")
    frame["close_time_ms"] = pd.to_numeric(frame["close_time_ms"], errors="coerce")
    return frame.dropna(subset=["open_time_ms", "close_time_ms", "close"])


def _write_cache(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip", float_format="%.12g")


@dataclass
class FetchResult:
    symbol: str
    status: str
    cache_path: str
    rows: int
    latest_close_time_utc: str | None
    raw_sha256: str | None = None
    cache_sha256: str | None = None
    error: str | None = None
    quality: dict[str, int] | None = None


def fetch_symbol(
    symbol: str,
    cache_root: Path,
    snapshot_dir: Path,
    cutoff: datetime,
    offline: bool,
    timeout_seconds: float = 20,
) -> FetchResult:
    cache_path = cache_root / "current" / "binance-spot-1d" / f"{symbol}.csv.gz"
    current = _read_cache(cache_path)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    if offline:
        if current.empty:
            return FetchResult(symbol, "MISSING_OFFLINE", str(cache_path), 0, None, error="cache missing")
        latest = pd.to_datetime(current["close_time_ms"].max(), unit="ms", utc=True)
        return FetchResult(
            symbol,
            "CACHE_ONLY",
            str(cache_path),
            int(len(current)),
            latest.isoformat(),
            cache_sha256=sha256_file(cache_path),
        )

    earliest_ms = cutoff_ms - FETCH_DAYS * DAY_MS
    if current.empty:
        start_ms = earliest_ms
    else:
        start_ms = max(earliest_ms, int(current["open_time_ms"].max()) - 3 * DAY_MS)
    params = {
        "symbol": symbol,
        "interval": "1d",
        "startTime": start_ms,
        "endTime": cutoff_ms,
        "timeZone": "0",
        "limit": 1000,
    }
    try:
        response = get_with_retry(BINANCE_URL, params=params, timeout=timeout_seconds)
        raw = response.content
        rows = response.json()
        normalized, quality = normalize_binance_klines(rows, cutoff_ms)
        raw_path = snapshot_dir / "raw" / "binance" / f"{symbol}.json.gz"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(raw_path, "wb") as handle:
            handle.write(raw)
        if current.empty:
            combined = normalized
        else:
            combined = pd.concat([current, normalized], ignore_index=True)
            combined = combined.drop_duplicates(subset=["open_time_ms"], keep="last")
            combined = combined[pd.to_numeric(combined["close_time_ms"], errors="coerce") <= cutoff_ms]
            combined = combined.sort_values("open_time_ms").tail(FETCH_DAYS + 5)
        if combined.empty:
            raise ValueError("endpoint returned no usable closed bars")
        _write_cache(combined, cache_path)
        latest = pd.to_datetime(combined["close_time_ms"].max(), unit="ms", utc=True)
        return FetchResult(
            symbol,
            "FETCHED",
            str(cache_path),
            int(len(combined)),
            latest.isoformat(),
            raw_sha256=sha256_bytes(raw),
            cache_sha256=sha256_file(cache_path),
            quality=quality,
        )
    except Exception as exc:  # network failures are surfaced and last-good cache is retained
        if not current.empty:
            latest = pd.to_datetime(current["close_time_ms"].max(), unit="ms", utc=True)
            return FetchResult(
                symbol,
                "STALE_CACHE_AFTER_ERROR",
                str(cache_path),
                int(len(current)),
                latest.isoformat(),
                cache_sha256=sha256_file(cache_path),
                error=f"{type(exc).__name__}: {exc}",
            )
        return FetchResult(
            symbol,
            "FAILED",
            str(cache_path),
            0,
            None,
            error=f"{type(exc).__name__}: {exc}",
        )


def fetch_coin_metrics(
    cache_root: Path,
    snapshot_dir: Path,
    cutoff: datetime,
    offline: bool,
) -> dict[str, Any]:
    cache_path = cache_root / "current" / "coin-metrics-price-usd.csv.gz"
    if offline:
        return {"status": "CACHE_ONLY" if cache_path.exists() else "MISSING_OFFLINE", "cache_path": str(cache_path)}
    start = (cutoff - timedelta(days=FETCH_DAYS + 5)).date().isoformat()
    base_params = {
        "metrics": COIN_METRICS_FIELD,
        "start_time": start,
        "end_time": cutoff.date().isoformat(),
        "frequency": "1d",
        "page_size": 10000,
    }
    frames: list[pd.DataFrame] = []
    asset_status: dict[str, Any] = {}
    for asset in sorted(set(ANCHOR_CROSSCHECK.values())):
        params = {**base_params, "assets": asset}
        try:
            response = get_with_retry(COIN_METRICS_URL, params=params, timeout=30, attempts=2)
            raw = response.content
            payload = response.json()
            records = payload.get("data", [])
            frame = pd.DataFrame(records)
            if frame.empty or COIN_METRICS_FIELD not in frame:
                raise ValueError(f"no Coin Metrics {COIN_METRICS_FIELD} data returned")
            frame[COIN_METRICS_FIELD] = pd.to_numeric(frame[COIN_METRICS_FIELD], errors="coerce")
            frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
            frame = frame.dropna(subset=["asset", "time", COIN_METRICS_FIELD])
            frame = frame[frame[COIN_METRICS_FIELD] > 0].sort_values(["asset", "time"])
            frames.append(frame[["asset", "time", COIN_METRICS_FIELD]])
            raw_path = snapshot_dir / "raw" / "coin-metrics" / f"{asset}-price-usd.json.gz"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(raw_path, "wb") as handle:
                handle.write(raw)
            asset_status[asset] = {"status": "FETCHED", "rows": len(frame), "raw_sha256": sha256_bytes(raw)}
        except Exception as exc:
            asset_status[asset] = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
    if frames:
        combined = pd.concat(frames, ignore_index=True).sort_values(["asset", "time"])
        _write_cache(combined, cache_path)
        return {
            "status": "FETCHED_WITH_GAPS" if any(item["status"] != "FETCHED" for item in asset_status.values()) else "FETCHED",
            "cache_path": str(cache_path),
            "rows": int(len(combined)),
            "cache_sha256": sha256_file(cache_path),
            "assets_returned": sorted(combined["asset"].unique().tolist()),
            "asset_status": asset_status,
        }
    return {
        "status": "STALE_CACHE_AFTER_ERROR" if cache_path.exists() else "FAILED",
        "cache_path": str(cache_path),
        "cache_sha256": sha256_file(cache_path) if cache_path.exists() else None,
        "asset_status": asset_status,
    }


def _price_series(cache_path: str | Path) -> pd.Series:
    frame = _read_cache(Path(cache_path))
    if frame.empty:
        return pd.Series(dtype=float)
    index = pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True)
    values = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
    series = pd.Series(values, index=index).replace([np.inf, -np.inf], np.nan).dropna()
    return series[series > 0][~series.index.duplicated(keep="last")].sort_index()


def aligned_daily_returns(asset_price: pd.Series, btc_price: pd.Series) -> pd.DataFrame:
    prices = pd.concat({"asset": asset_price, "btc": btc_price}, axis=1, join="inner").dropna()
    log_returns = np.log(prices).diff()
    consecutive = prices.index.to_series().diff() == pd.Timedelta(days=1)
    return log_returns[consecutive].replace([np.inf, -np.inf], np.nan).dropna()


def _correlation(values: pd.DataFrame) -> float:
    if len(values) < 3 or values["asset"].std(ddof=1) == 0 or values["btc"].std(ddof=1) == 0:
        return math.nan
    return float(values["asset"].corr(values["btc"], method="pearson"))


def analyze_pair(symbol: str, asset_price: pd.Series, btc_price: pd.Series) -> tuple[dict[str, Any], pd.Series]:
    returns = aligned_daily_returns(asset_price, btc_price)
    main = returns.tail(MAIN_WINDOW)
    if len(main) < MIN_OBS:
        return {
            "symbol": symbol,
            "status": "INSUFFICIENT_SAMPLE",
            "n_obs": int(len(main)),
            "first_return_utc": main.index.min().isoformat() if len(main) else None,
            "last_return_utc": main.index.max().isoformat() if len(main) else None,
        }, pd.Series(dtype=float)
    pearson = _correlation(main)
    spearman = float(stats.spearmanr(main["asset"], main["btc"]).statistic)
    design = sm.add_constant(main["btc"].to_numpy(dtype=float), has_constant="add")
    base_fit = sm.OLS(main["asset"].to_numpy(dtype=float), design).fit()
    robust = base_fit.get_robustcov_results(
        cov_type="HAC",
        maxlags=HAC_LAGS,
        kernel="bartlett",
        use_correction=True,
        use_t=True,
    )
    recent = returns.tail(SUB_WINDOW)
    prior = returns.iloc[-2 * SUB_WINDOW : -SUB_WINDOW]
    recent_corr = _correlation(recent) if len(recent) >= MIN_SUB_OBS else math.nan
    prior_corr = _correlation(prior) if len(prior) >= MIN_SUB_OBS else math.nan
    volatility_ratio = float(main["asset"].std(ddof=1) / main["btc"].std(ddof=1))
    rolling = returns["asset"].rolling(ROLLING_WINDOW, min_periods=ROLLING_MIN_OBS).corr(returns["btc"])
    result: dict[str, Any] = {
        "symbol": symbol,
        "status": "ANALYZED",
        "n_obs": int(len(main)),
        "first_return_utc": main.index.min().isoformat(),
        "last_return_utc": main.index.max().isoformat(),
        "pearson": pearson,
        "spearman": spearman,
        "beta": float(robust.params[1]),
        "beta_ci_low": float(robust.conf_int(alpha=0.05)[1, 0]),
        "beta_ci_high": float(robust.conf_int(alpha=0.05)[1, 1]),
        "beta_p_hac": float(robust.pvalues[1]),
        "alpha_daily": float(robust.params[0]),
        "r_squared": float(base_fit.rsquared),
        "volatility_ratio": volatility_ratio,
        "residual_volatility_annualized": float(np.std(base_fit.resid, ddof=1) * math.sqrt(365)),
        "recent_180_pearson": recent_corr,
        "prior_180_pearson": prior_corr,
        "window_correlation_delta": (
            abs(recent_corr - prior_corr) if math.isfinite(recent_corr) and math.isfinite(prior_corr) else math.nan
        ),
    }
    for horizon in (7, 30, 90):
        key = f"relative_strength_{horizon}d"
        result[key] = (
            float(math.expm1((returns["asset"] - returns["btc"]).tail(horizon).sum()))
            if len(returns) >= horizon
            else math.nan
        )
    return result, rolling.dropna()


def apply_multiple_testing(results: list[dict[str, Any]]) -> None:
    analyzable = [row for row in results if row.get("status") == "ANALYZED" and math.isfinite(row["beta_p_hac"])]
    if not analyzable:
        return
    reject, adjusted, _, _ = multipletests(
        [row["beta_p_hac"] for row in analyzable],
        alpha=FDR_ALPHA,
        method="fdr_by",
    )
    for row, is_rejected, q_value in zip(analyzable, reject, adjusted, strict=True):
        row["q_value_by"] = float(q_value)
        row["statistically_significant"] = bool(is_rejected)
        signs = [
            np.sign(row["pearson"]),
            np.sign(row["spearman"]),
            np.sign(row["recent_180_pearson"]),
            np.sign(row["prior_180_pearson"]),
        ]
        stable_sign = all(math.isfinite(float(value)) and value != 0 and value == signs[0] for value in signs)
        row["stable_sign"] = bool(stable_sign)
        row["strong_association"] = bool(
            is_rejected and abs(row["pearson"]) >= STRONG_CORRELATION and stable_sign
        )
        magnitude = abs(row["pearson"])
        row["association_band"] = (
            "VERY_STRONG" if magnitude >= 0.70 else "STRONG" if magnitude >= 0.50 else "MODERATE" if magnitude >= 0.30 else "WEAK"
        )
    for row in results:
        if row.get("status") != "ANALYZED":
            row.update(
                {
                    "q_value_by": math.nan,
                    "statistically_significant": False,
                    "stable_sign": False,
                    "strong_association": False,
                    "association_band": "NOT_EVALUATED",
                }
            )


def crosscheck_coin_metrics(cache_path: str | Path, binance_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = Path(cache_path)
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    if frame.empty:
        return []
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame[COIN_METRICS_FIELD] = pd.to_numeric(frame[COIN_METRICS_FIELD], errors="coerce")
    prices = {
        asset: group.set_index("time")[COIN_METRICS_FIELD].dropna().sort_index()
        for asset, group in frame.groupby("asset")
    }
    if "btc" not in prices:
        return []
    by_symbol = {row["symbol"]: row for row in binance_results if row.get("status") == "ANALYZED"}
    checks: list[dict[str, Any]] = []
    for symbol, asset in ANCHOR_CROSSCHECK.items():
        if symbol == REFERENCE_SYMBOL:
            continue
        if asset not in prices:
            checks.append({"symbol": symbol, "status": "UNAVAILABLE_FROM_COIN_METRICS_COMMUNITY"})
            continue
        if symbol not in by_symbol:
            checks.append({"symbol": symbol, "status": "PRIMARY_NOT_ANALYZED"})
            continue
        cm_result, _ = analyze_pair(symbol, prices[asset], prices["btc"])
        if cm_result.get("status") != "ANALYZED":
            checks.append({"symbol": symbol, "status": cm_result.get("status"), "n_obs": cm_result.get("n_obs")})
            continue
        primary = by_symbol[symbol]
        checks.append(
            {
                "symbol": symbol,
                "status": "COMPARED",
                "coin_metrics_n_obs": cm_result["n_obs"],
                "binance_pearson": primary["pearson"],
                "coin_metrics_pearson": cm_result["pearson"],
                "pearson_delta": abs(primary["pearson"] - cm_result["pearson"]),
                "binance_beta": primary["beta"],
                "coin_metrics_beta": cm_result["beta"],
                "beta_delta": abs(primary["beta"] - cm_result["beta"]),
                "direction_agreement": bool(np.sign(primary["pearson"]) == np.sign(cm_result["pearson"])),
            }
        )
    return checks


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if pd.isna(value):
        return None
    return value


def _write_outputs(
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    manifest: dict[str, Any],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(results).sort_values(
        ["statistically_significant", "strong_association", "pearson", "symbol"],
        ascending=[False, False, False, True],
        na_position="last",
    )
    frame.to_csv(output_dir / "results.csv", index=False, float_format="%.10g", quoting=csv.QUOTE_MINIMAL)
    frame[frame["statistically_significant"] == True].to_csv(  # noqa: E712 - explicit CSV boolean filter
        output_dir / "significant-associations.csv", index=False, float_format="%.10g", quoting=csv.QUOTE_MINIMAL
    )
    frame[frame["strong_association"] == True].to_csv(  # noqa: E712 - explicit CSV boolean filter
        output_dir / "strong-associations.csv", index=False, float_format="%.10g", quoting=csv.QUOTE_MINIMAL
    )
    frame[frame["status"] != "ANALYZED"].to_csv(
        output_dir / "not-analyzed.csv", index=False, float_format="%.10g", quoting=csv.QUOTE_MINIMAL
    )
    (output_dir / "summary.json").write_text(
        json.dumps(_json_safe(summary), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "data-manifest.json").write_text(
        json.dumps(_json_safe(manifest), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def refresh(
    cache_root: Path = DEFAULT_CACHE_ROOT,
    offline: bool = False,
    workers: int = 8,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    started = utc_now()
    cutoff = latest_closed_cutoff(started)
    refresh_id = started.strftime("%Y-%m-%dT%H%M%SZ")
    snapshot_dir = cache_root / "snapshots" / refresh_id
    universe, universe_identity = load_universe()
    symbols = universe["symbol"].tolist()
    fetch_results: dict[str, FetchResult] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        futures = {
            pool.submit(fetch_symbol, symbol, cache_root, snapshot_dir, cutoff, offline): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            result = future.result()
            fetch_results[result.symbol] = result
    coin_metrics = fetch_coin_metrics(cache_root, snapshot_dir, cutoff, offline)
    reference_fetch = fetch_results.get(REFERENCE_SYMBOL)
    if reference_fetch is None or reference_fetch.rows == 0:
        raise RuntimeError("BTC reference data unavailable; no result was written")
    btc_price = _price_series(reference_fetch.cache_path)
    results: list[dict[str, Any]] = []
    rolling_cache: dict[str, list[dict[str, Any]]] = {}
    metadata = universe.set_index("symbol").to_dict(orient="index")
    for symbol in symbols:
        if symbol == REFERENCE_SYMBOL:
            continue
        fetched = fetch_results[symbol]
        if fetched.rows == 0:
            row = {"symbol": symbol, "status": "FETCH_FAILED", "n_obs": 0}
            rolling = pd.Series(dtype=float)
        else:
            row, rolling = analyze_pair(symbol, _price_series(fetched.cache_path), btc_price)
        row.update(
            {
                "base_asset": metadata[symbol]["base_asset"],
                "economic_exposure": metadata[symbol]["economic_exposure"],
                "economic_exposure_source": metadata[symbol]["economic_exposure_source"],
                "classification_subtypes": metadata[symbol]["classification_subtypes"],
                "research_bucket": metadata[symbol]["research_bucket"],
                "activity_tier_24h": metadata[symbol]["activity_tier_24h"],
                "risk_flags": metadata[symbol]["risk_flags"],
                "fetch_status": fetched.status,
            }
        )
        results.append(row)
        if not rolling.empty:
            rolling_cache[symbol] = [
                {"time": index.isoformat(), "pearson": float(value)} for index, value in rolling.items()
            ]
    apply_multiple_testing(results)
    crosschecks = crosscheck_coin_metrics(coin_metrics.get("cache_path", ""), results)
    analyzed = [row for row in results if row["status"] == "ANALYZED"]
    significant = [row for row in analyzed if row["statistically_significant"]]
    strong = [row for row in analyzed if row["strong_association"]]
    failed = [result for result in fetch_results.values() if result.status in {"FAILED", "MISSING_OFFLINE"}]
    stale = [result for result in fetch_results.values() if result.status == "STALE_CACHE_AFTER_ERROR"]
    status = "OK"
    if failed or stale or coin_metrics.get("status") in {"FAILED", "STALE_CACHE_AFTER_ERROR", "MISSING_OFFLINE"}:
        status = "PARTIAL"
    if len(analyzed) < max(1, int(universe_identity["eligible_objects"] * 0.8)):
        status = "INSUFFICIENT_COVERAGE"
    summary = {
        "question": "Which current Binance Spot USDT crypto assets are significantly and strongly associated with BTC?",
        "research_type": "COMPARATIVE_OR_MECHANISM",
        "method_version": "1.0.0",
        "generated_at_utc": iso_z(utc_now()),
        "data_cutoff_utc": iso_z(cutoff),
        "universe": universe_identity,
        "status": status,
        "counts": {
            "eligible_objects": universe_identity["eligible_objects"],
            "analyzed": len(analyzed),
            "insufficient_sample": sum(row["status"] == "INSUFFICIENT_SAMPLE" for row in results),
            "fetch_failed": len(failed),
            "stale_cache": len(stale),
            "statistically_significant": len(significant),
            "strong_association": len(strong),
        },
        "median_beta": float(np.median([row["beta"] for row in analyzed])) if analyzed else None,
        "method": {
            "price": "Binance Spot USDT 1d closed UTC klines",
            "returns": "consecutive aligned close-to-close log returns",
            "main_window": MAIN_WINDOW,
            "minimum_observations": MIN_OBS,
            "inference": "OLS beta; HAC Bartlett maxlags=7 small-sample correction; two-sided t inference",
            "multiplicity": "Benjamini-Yekutieli FDR q<=0.05 across all analyzed symbols",
            "strong_rule": "significant; abs(Pearson)>=0.50; Pearson/Spearman/recent180/prior180 same non-zero sign",
            "relative_strength": "exp(sum(asset log return - BTC log return))-1 over 7/30/90 days",
        },
        "cross_source_checks": crosschecks,
        "failures": [result.__dict__ for result in sorted(failed + stale, key=lambda item: item.symbol)],
        "top_strong": sorted(strong, key=lambda row: abs(row["pearson"]), reverse=True)[:20],
        "warnings": [
            "Current-list survivorship: the universe is not reconstructed point-in-time.",
            "Association is not causation, lead-lag, prediction, strategy evidence, or Alpha.",
            "Daily single-venue closes do not identify intraday spillovers or execution quality.",
        ],
    }
    source_manifest = {
        "refresh_id": refresh_id,
        "started_at_utc": iso_z(started),
        "completed_at_utc": iso_z(utc_now()),
        "offline": offline,
        "binance_endpoint": BINANCE_URL,
        "coin_metrics_endpoint": COIN_METRICS_URL,
        "coin_metrics_metric": COIN_METRICS_FIELD,
        "universe": universe_identity,
        "binance": [fetch_results[symbol].__dict__ for symbol in sorted(fetch_results)],
        "coin_metrics": coin_metrics,
    }
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = snapshot_dir / "source-manifest.json"
    manifest_path.write_text(json.dumps(_json_safe(source_manifest), indent=2) + "\n", encoding="utf-8")
    manifest = {
        "source_manifest_path": str(manifest_path.resolve()),
        "source_manifest_sha256": sha256_file(manifest_path),
        "cache_root": str(cache_root.resolve()),
        "universe": universe_identity,
        "cutoff_utc": iso_z(cutoff),
        "result_rows": len(results),
        "result_identity_note": (
            "Analytical result columns reproduce from the recorded cache and offline command; "
            "fetch_status and source-manifest identity intentionally record whether the run was online or offline."
        ),
    }
    _write_outputs(results, summary, manifest, output_dir or cache_root / "live")
    rolling_path = cache_root / "current" / "rolling-90d.json.gz"
    rolling_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(rolling_path, "wt", encoding="utf-8") as handle:
        json.dump(rolling_cache, handle, separators=(",", ":"))
    return summary


class MonitorState:
    def __init__(self, cache_root: Path, output_dir: Path, refresh_seconds: int, workers: int) -> None:
        self.cache_root = cache_root
        self.output_dir = output_dir
        self.refresh_seconds = refresh_seconds
        self.workers = workers
        self.lock = threading.Lock()
        self.last_error: str | None = None
        self.last_attempt: str | None = None
        self.next_attempt: str | None = None

    def run_refresh(self) -> None:
        if not self.lock.acquire(blocking=False):
            return
        try:
            self.last_attempt = iso_z(utc_now())
            refresh(self.cache_root, offline=False, workers=self.workers, output_dir=self.output_dir)
            self.last_error = None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            self.next_attempt = iso_z(utc_now() + timedelta(seconds=self.refresh_seconds))
            self.lock.release()

    def result_path(self, name: str) -> Path:
        live_path = self.output_dir / name
        return live_path if live_path.exists() else EVIDENCE_DIR / name


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def make_handler(state: MonitorState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "HalphaResearchMonitor/1.0"

        def _send(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            # Plotly applies calculated layout through element.style. Scripts
            # remain self-hosted; only inline CSS is permitted.
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(
                json.dumps(_json_safe(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/favicon.ico":
                self._send(b"", "image/x-icon", HTTPStatus.NO_CONTENT)
                return
            if parsed.path == "/":
                self._send((APP_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
                return
            if parsed.path == "/app.js":
                self._send((APP_DIR / "app.js").read_bytes(), "application/javascript; charset=utf-8")
                return
            if parsed.path == "/styles.css":
                self._send((APP_DIR / "styles.css").read_bytes(), "text/css; charset=utf-8")
                return
            if parsed.path == "/plotly.min.js":
                self._send(plotly.offline.get_plotlyjs().encode("utf-8"), "application/javascript; charset=utf-8")
                return
            if parsed.path == "/api/summary":
                path = state.result_path("summary.json")
                if not path.exists():
                    self._json({"status": "NOT_READY", "last_error": state.last_error}, HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                payload = _load_json(path)
                payload["monitor"] = {
                    "refresh_in_progress": state.lock.locked(),
                    "last_attempt_utc": state.last_attempt,
                    "next_attempt_utc": state.next_attempt,
                    "last_error": state.last_error,
                }
                self._json(payload)
                return
            if parsed.path == "/api/results":
                path = state.result_path("results.csv")
                if not path.exists():
                    self._json({"error": "results not ready"}, HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                frame = pd.read_csv(path)
                self._json(frame.replace({np.nan: None}).to_dict(orient="records"))
                return
            if parsed.path == "/api/detail":
                symbol = parse_qs(parsed.query).get("symbol", [""])[0].upper()
                if not symbol.isalnum() or len(symbol) > 30:
                    self._json({"error": "invalid symbol"}, HTTPStatus.BAD_REQUEST)
                    return
                rolling_path = state.cache_root / "current" / "rolling-90d.json.gz"
                if not rolling_path.exists():
                    self._json({"symbol": symbol, "rolling": []})
                    return
                with gzip.open(rolling_path, "rt", encoding="utf-8") as handle:
                    rolling = json.load(handle).get(symbol, [])
                self._json({"symbol": symbol, "rolling": rolling})
                return
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/refresh":
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            if state.lock.locked():
                self._json({"status": "ALREADY_REFRESHING"}, HTTPStatus.ACCEPTED)
                return
            threading.Thread(target=state.run_refresh, daemon=True).start()
            self._json({"status": "REFRESH_STARTED"}, HTTPStatus.ACCEPTED)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"[{iso_z(utc_now())}] {self.address_string()} {format % args}")

    return Handler


def serve(
    host: str,
    port: int,
    cache_root: Path,
    refresh_seconds: int,
    workers: int,
    no_initial_refresh: bool,
    output_dir: Path | None = None,
) -> None:
    state = MonitorState(cache_root, output_dir or cache_root / "live", refresh_seconds, workers)
    # Bind before refreshing so a persisted, validated snapshot is available
    # immediately. The public-data refresh can take around a minute for the
    # current universe and must not make the local page appear unavailable.
    server = ThreadingHTTPServer((host, port), make_handler(state))
    if not no_initial_refresh:
        threading.Thread(target=state.run_refresh, daemon=True).start()

    def background() -> None:
        while True:
            state.next_attempt = iso_z(utc_now() + timedelta(seconds=refresh_seconds))
            time.sleep(refresh_seconds)
            state.run_refresh()

    threading.Thread(target=background, daemon=True).start()
    print(f"BTC relationship monitor: http://{host}:{port}")
    print("Metrics use closed daily bars; polling does not create intraday metric changes.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["refresh", "serve"])
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Mutable result directory; defaults to <cache-root>/live outside Git.",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--offline", action="store_true", help="Use only recorded caches (refresh command only).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--refresh-seconds", type=int, default=900)
    parser.add_argument("--no-initial-refresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "refresh":
        summary = refresh(args.cache_root, args.offline, args.workers, args.output_dir)
        print(json.dumps(_json_safe(summary["counts"]), ensure_ascii=False, indent=2))
        print(f"status={summary['status']} cutoff={summary['data_cutoff_utc']}")
        return 0 if summary["status"] in {"OK", "PARTIAL"} else 2
    if args.offline:
        raise SystemExit("--offline applies only to refresh")
    serve(
        args.host,
        args.port,
        args.cache_root,
        args.refresh_seconds,
        args.workers,
        args.no_initial_refresh,
        args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
