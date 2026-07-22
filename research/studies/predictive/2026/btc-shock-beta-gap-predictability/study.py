from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import math
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import statsmodels.api as sm
import vectorbt as vbt
from statsmodels.stats.multitest import multipletests


STUDY_DIR = Path(__file__).resolve().parent
CHECKPOINT_PATH = STUDY_DIR / "checkpoint.json"
DATA_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "btc-shock-beta-gap-predictability"
)
RAW_ROOT = DATA_ROOT / "raw"

ANCHOR = "BTCUSDT"
ALTS = [
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "TRXUSDT",
    "DOTUSDT",
    "NEARUSDT",
    "SUIUSDT",
    "AAVEUSDT",
]
SYMBOLS = [ANCHOR, *ALTS]
INTERVAL = "5m"
BARS_PER_DAY = 24 * 12
SHOCK_WINDOW_BARS = 30 * BARS_PER_DAY
COOLDOWN_BARS = 6
BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines"

PHASES = {
    "development": {
        "prepare_start": "2023-10-01",
        "start": "2024-01-01",
        "end": "2025-01-01",
    },
    "evaluation": {
        "prepare_start": "2025-01-01",
        "start": "2025-01-01",
        "end": "2026-01-01",
    },
    "confirmation": {
        "prepare_start": "2026-01-01",
        "start": "2026-01-01",
        "end": "2026-07-01",
    },
}

KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base",
    "taker_buy_quote",
    "ignore",
]


@dataclass(frozen=True)
class Config:
    name: str
    beta_days: int = 30
    shock_quantile: float = 0.975
    horizon_bars: int = 3
    entry_delay_bars: int = 1


CONFIGS = [
    Config("primary"),
    Config("beta_7d", beta_days=7),
    Config("beta_90d", beta_days=90),
    Config("shock_q95", shock_quantile=0.95),
    Config("shock_q99", shock_quantile=0.99),
    Config("horizon_5m", horizon_bars=1),
    Config("horizon_30m", horizon_bars=6),
    Config("extra_5m_latency", entry_delay_bars=2),
]


def load_checkpoint() -> dict[str, Any]:
    return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))


def code_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def verify_plan() -> None:
    checkpoint = load_checkpoint()
    expected = checkpoint["study_code_sha256"]
    actual = code_sha256()
    failures: list[str] = []
    if checkpoint["anchor"] != ANCHOR:
        failures.append("anchor differs from checkpoint")
    if checkpoint["symbols"] != ALTS:
        failures.append("symbol order differs from checkpoint")
    if checkpoint["bar_interval"] != INTERVAL:
        failures.append("interval differs from checkpoint")
    primary = checkpoint["primary"]
    expected_primary = {
        "beta_window_days": 30,
        "shock_quantile": 0.975,
        "shock_window_days": 30,
        "cooldown_bars": 6,
        "target_horizon_bars": 3,
        "entry_delay_bars": 1,
    }
    if primary != expected_primary:
        failures.append("primary configuration differs from checkpoint")
    if expected == "PENDING_BEFORE_FIRST_DOWNLOAD":
        failures.append(f"checkpoint code hash is pending; actual is {actual}")
    elif expected != actual:
        failures.append(f"code hash mismatch: checkpoint={expected}, actual={actual}")
    if failures:
        raise RuntimeError("; ".join(failures))
    print(
        json.dumps(
            {
                "status": "PASS",
                "study_code_sha256": actual,
                "pandas": pd.__version__,
                "numpy": np.__version__,
                "statsmodels": sm.__version__,
                "vectorbt": vbt.__version__,
            },
            indent=2,
        )
    )


def month_starts(start: str, end: str) -> list[pd.Timestamp]:
    return list(
        pd.date_range(
            pd.Timestamp(start, tz="UTC"),
            pd.Timestamp(end, tz="UTC"),
            freq="MS",
            inclusive="left",
        )
    )


def required_months_for_run(phase: str) -> list[pd.Timestamp]:
    return month_starts(PHASES["development"]["prepare_start"], PHASES[phase]["end"])


def phase_prepare_months(phase: str) -> list[pd.Timestamp]:
    spec = PHASES[phase]
    return month_starts(spec["prepare_start"], spec["end"])


def source_paths(symbol: str, month: pd.Timestamp) -> tuple[Path, Path, str, str]:
    stamp = month.strftime("%Y-%m")
    filename = f"{symbol}-{INTERVAL}-{stamp}.zip"
    relative_url = f"{symbol}/{INTERVAL}/{filename}"
    url = f"{BASE_URL}/{relative_url}"
    local = RAW_ROOT / symbol / filename
    return local, local.with_suffix(local.suffix + ".CHECKSUM"), url, url + ".CHECKSUM"


def fetch_bytes(url: str, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    request = urllib.request.Request(url, headers={"User-Agent": "Halpha-research/1.0"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (
            urllib.error.URLError,
            http.client.IncompleteRead,
            TimeoutError,
            OSError,
        ) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"download failed after {attempts} attempts: {url}: {last_error}")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def expected_checksum(payload: bytes, filename: str) -> str:
    text = payload.decode("utf-8").strip()
    parts = text.split()
    if len(parts) < 2 or parts[1].lstrip("*") != filename:
        raise ValueError(f"unexpected CHECKSUM format for {filename}: {text!r}")
    digest = parts[0].lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"invalid SHA-256 in CHECKSUM for {filename}")
    return digest


def validate_archive(payload: bytes, filename: str) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = [item for item in archive.namelist() if not item.endswith("/")]
        if len(members) != 1 or not members[0].endswith(".csv"):
            raise ValueError(f"{filename} must contain exactly one CSV, got {members}")
        bad = archive.testzip()
        if bad is not None:
            raise ValueError(f"corrupt member {bad} in {filename}")
        return {"zip_member": members[0]}


def prepare_one(symbol: str, month: pd.Timestamp) -> dict[str, Any]:
    local, checksum_local, url, checksum_url = source_paths(symbol, month)
    local.parent.mkdir(parents=True, exist_ok=True)
    checksum_payload = fetch_bytes(checksum_url)
    expected = expected_checksum(checksum_payload, local.name)

    if local.exists() and sha256_bytes(local.read_bytes()) == expected:
        payload = local.read_bytes()
        disposition = "reused_verified_cache"
    else:
        payload = fetch_bytes(url)
        actual = sha256_bytes(payload)
        if actual != expected:
            raise ValueError(
                f"checksum mismatch for {local.name}: expected={expected}, actual={actual}"
            )
        local.write_bytes(payload)
        disposition = "downloaded"

    actual = sha256_bytes(payload)
    if actual != expected:
        raise ValueError(
            f"checksum mismatch after cache write for {local.name}: "
            f"expected={expected}, actual={actual}"
        )
    checksum_local.write_bytes(checksum_payload)
    archive_meta = validate_archive(payload, local.name)
    return {
        "symbol": symbol,
        "month": month.strftime("%Y-%m"),
        "url": url,
        "checksum_url": checksum_url,
        "official_sha256": expected,
        "actual_sha256": actual,
        "bytes": len(payload),
        "cache_relative_path": local.relative_to(DATA_ROOT).as_posix(),
        "disposition": disposition,
        **archive_meta,
    }


def prior_phase_allows(phase: str) -> bool:
    if phase == "development":
        return True
    prior = "development" if phase == "evaluation" else "evaluation"
    prior_path = STUDY_DIR / f"{prior}.json"
    if not prior_path.exists():
        return False
    prior_result = json.loads(prior_path.read_text(encoding="utf-8"))
    return bool(prior_result.get("release_next_phase"))


def prepare(phase: str, workers: int) -> None:
    verify_plan()
    if not prior_phase_allows(phase):
        raise RuntimeError(f"{phase} remains sealed because the prior phase did not release it")
    tasks = [(symbol, month) for symbol in SYMBOLS for month in phase_prepare_months(phase)]
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as executor:
        future_map = {
            executor.submit(prepare_one, symbol, month): (symbol, month)
            for symbol, month in tasks
        }
        for future in as_completed(future_map):
            symbol, month = future_map[future]
            try:
                records.append(future.result())
            except Exception as exc:  # preserve every source-level failure
                failures.append(
                    {
                        "symbol": symbol,
                        "month": month.strftime("%Y-%m"),
                        "error": repr(exc),
                    }
                )
            completed = len(records) + len(failures)
            if completed % 25 == 0 or completed == len(tasks):
                print(f"prepare {phase}: {completed}/{len(tasks)}")

    manifest = {
        "phase": phase,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "Binance official USD-M monthly 5m Kline archive",
        "data_root": DATA_ROOT.as_posix(),
        "study_code_sha256": code_sha256(),
        "file_count": len(records),
        "total_bytes": sum(item["bytes"] for item in records),
        "failures": sorted(failures, key=lambda item: (item["symbol"], item["month"])),
        "files": sorted(records, key=lambda item: (item["symbol"], item["month"])),
    }
    manifest_path = STUDY_DIR / f"source_manifest_{phase}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if failures:
        raise RuntimeError(
            f"{len(failures)} source files failed; inspect {manifest_path.name}"
        )
    print(json.dumps({"status": "PASS", "manifest": str(manifest_path), "files": len(records)}))


def read_month(symbol: str, month: pd.Timestamp) -> pd.DataFrame:
    local, _, _, _ = source_paths(symbol, month)
    if not local.exists():
        raise FileNotFoundError(local)
    with zipfile.ZipFile(local) as archive:
        member = [name for name in archive.namelist() if name.endswith(".csv")][0]
        payload = archive.read(member)
    frame = pd.read_csv(io.BytesIO(payload), header=None, low_memory=False)
    if frame.shape[1] != len(KLINE_COLUMNS):
        raise ValueError(f"{local.name} has {frame.shape[1]} columns, expected 12")
    frame.columns = KLINE_COLUMNS
    numeric_time = pd.to_numeric(frame["open_time"], errors="coerce")
    if numeric_time.isna().iloc[0]:
        frame = frame.iloc[1:].copy()
        numeric_time = pd.to_numeric(frame["open_time"], errors="raise")
    else:
        frame = frame.copy()
    if numeric_time.isna().any():
        raise ValueError(f"non-numeric open_time in {local.name}")
    unit = "us" if float(numeric_time.max()) > 100_000_000_000_000 else "ms"
    frame.index = pd.to_datetime(numeric_time.astype("int64"), unit=unit, utc=True)
    for column in ["open", "close", "quote_volume", "trade_count"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"duplicate or unsorted timestamps in {local.name}")
    next_month = month + pd.offsets.MonthBegin(1)
    expected = pd.date_range(month, next_month, freq="5min", inclusive="left")
    if not frame.index.equals(expected):
        missing = expected.difference(frame.index)
        extra = frame.index.difference(expected)
        raise ValueError(
            f"grid mismatch in {local.name}: rows={len(frame)}, expected={len(expected)}, "
            f"missing={len(missing)}, extra={len(extra)}"
        )
    if (
        (~np.isfinite(frame[["open", "close"]])).any().any()
        or (frame[["open", "close"]] <= 0).any().any()
    ):
        raise ValueError(f"invalid open/close in {local.name}")
    return frame[["open", "close", "quote_volume", "trade_count"]]


def load_matrices(phase: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    months = required_months_for_run(phase)
    opens: dict[str, pd.Series] = {}
    closes: dict[str, pd.Series] = {}
    quote_volumes: dict[str, pd.Series] = {}
    trades: dict[str, pd.Series] = {}
    quality: dict[str, Any] = {"status": "PASS", "symbols": {}}
    reference_index: pd.DatetimeIndex | None = None
    for symbol in SYMBOLS:
        parts = [read_month(symbol, month) for month in months]
        frame = pd.concat(parts)
        if reference_index is None:
            reference_index = frame.index
        elif not frame.index.equals(reference_index):
            raise ValueError(f"{symbol} is not aligned to {ANCHOR}")
        opens[symbol] = frame["open"]
        closes[symbol] = frame["close"]
        quote_volumes[symbol] = frame["quote_volume"]
        trades[symbol] = frame["trade_count"]
        quality["symbols"][symbol] = {
            "rows": int(len(frame)),
            "first": frame.index[0].isoformat(),
            "last": frame.index[-1].isoformat(),
            "missing": 0,
            "duplicates": 0,
        }
    matrices = {
        "open": pd.DataFrame(opens),
        "close": pd.DataFrame(closes),
        "quote_volume": pd.DataFrame(quote_volumes),
        "trade_count": pd.DataFrame(trades),
    }
    quality["aligned_rows"] = int(len(matrices["close"]))
    return matrices, quality


def select_events(raw_condition: pd.Series, cooldown_bars: int) -> pd.DatetimeIndex:
    values = raw_condition.fillna(False).to_numpy(dtype=bool)
    positions = np.flatnonzero(values)
    selected: list[int] = []
    last = -10**12
    for position in positions:
        if position - last > cooldown_bars:
            selected.append(int(position))
            last = int(position)
    return raw_condition.index[np.asarray(selected, dtype=int)]


def rolling_beta(alt_returns: pd.DataFrame, btc_returns: pd.Series, days: int) -> pd.DataFrame:
    window = days * BARS_PER_DAY
    btc_var = btc_returns.rolling(window, min_periods=window).var().shift(1)
    result: dict[str, pd.Series] = {}
    for symbol in ALTS:
        covariance = (
            alt_returns[symbol]
            .rolling(window, min_periods=window)
            .cov(btc_returns)
            .shift(1)
        )
        result[symbol] = covariance / btc_var
    return pd.DataFrame(result)


def future_residual(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    beta: pd.DataFrame,
    horizon_bars: int,
    entry_delay_bars: int,
) -> pd.DataFrame:
    end_shift = entry_delay_bars + horizon_bars - 1
    alt_move = np.log(
        closes[ALTS].shift(-end_shift) / opens[ALTS].shift(-entry_delay_bars)
    )
    btc_move = np.log(
        closes[ANCHOR].shift(-end_shift) / opens[ANCHOR].shift(-entry_delay_bars)
    )
    return alt_move.subtract(beta.mul(btc_move, axis=0))


def cluster_summary(values: pd.Series) -> dict[str, Any]:
    series = values.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    if series.empty:
        return {
            "n": 0,
            "mean_bps": None,
            "median_bps": None,
            "win_rate": None,
            "ci_low_bps": None,
            "ci_high_bps": None,
            "p_value_two_sided": None,
            "cluster_days": 0,
        }
    groups = pd.Index(series.index.date)
    if groups.nunique() >= 2 and len(series) >= 3:
        fit = sm.OLS(series.to_numpy(), np.ones((len(series), 1))).fit(
            cov_type="cluster",
            cov_kwds={"groups": groups.to_numpy(), "use_correction": True},
        )
        ci = fit.conf_int(alpha=0.05)[0]
        p_value = float(fit.pvalues[0])
        low, high = float(ci[0]), float(ci[1])
    else:
        p_value = math.nan
        low = high = math.nan
    return {
        "n": int(len(series)),
        "mean_bps": float(series.mean() * 10_000),
        "median_bps": float(series.median() * 10_000),
        "win_rate": float((series > 0).mean()),
        "ci_low_bps": None if math.isnan(low) else float(low * 10_000),
        "ci_high_bps": None if math.isnan(high) else float(high * 10_000),
        "p_value_two_sided": None if math.isnan(p_value) else p_value,
        "cluster_days": int(groups.nunique()),
    }


def event_level_series(
    matrix: pd.DataFrame,
    mask: pd.DataFrame,
    events: pd.DatetimeIndex,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    event_matrix = matrix.loc[events, ALTS].where(mask.loc[events, ALTS])
    mean = event_matrix.mean(axis=1, skipna=True).dropna()
    used = event_matrix.notna().sum(axis=1).reindex(mean.index)
    available = matrix.loc[events, ALTS].notna().sum(axis=1).reindex(mean.index)
    return mean, used, available


def analyze_config(
    config: Config,
    matrices: dict[str, pd.DataFrame],
    phase: str,
    beta_cache: dict[int, pd.DataFrame],
    shock_cache: dict[float, pd.DatetimeIndex],
) -> tuple[dict[str, Any], dict[str, Any]]:
    opens = matrices["open"]
    closes = matrices["close"]
    returns = np.log(closes).diff()
    btc_returns = returns[ANCHOR]
    alt_returns = returns[ALTS]
    beta = beta_cache[config.beta_days]
    events = shock_cache[config.shock_quantile]
    start = pd.Timestamp(PHASES[phase]["start"], tz="UTC")
    end = pd.Timestamp(PHASES[phase]["end"], tz="UTC")
    events = events[(events >= start) & (events < end)]

    residual = future_residual(
        opens,
        closes,
        beta,
        horizon_bars=config.horizon_bars,
        entry_delay_bars=config.entry_delay_bars,
    )
    gap = beta.mul(btc_returns, axis=0) - alt_returns
    underreaction = np.sign(gap).eq(np.sign(btc_returns), axis=0) & gap.ne(0)
    response = np.sign(gap) * residual
    primary_events, used_assets, available_assets = event_level_series(
        response, underreaction & residual.notna(), events
    )

    btc_direction_response = residual.mul(np.sign(btc_returns), axis=0)
    btc_baseline, _, _ = event_level_series(
        btc_direction_response, residual.notna(), events
    )
    own_direction_response = np.sign(alt_returns) * residual
    own_baseline, _, _ = event_level_series(
        own_direction_response, residual.notna() & alt_returns.notna(), events
    )

    result: dict[str, Any] = {
        "config": asdict(config),
        "event_count_raw": int(len(events)),
        "event_count_with_underreaction": int(len(primary_events)),
        "mean_underreaction_assets_per_event": (
            float(used_assets.mean()) if len(used_assets) else None
        ),
        "mean_available_assets_per_event": (
            float(available_assets.mean()) if len(available_assets) else None
        ),
        "primary": cluster_summary(primary_events),
        "baselines": {
            "btc_sign": cluster_summary(btc_baseline),
            "own_return_sign": cluster_summary(own_baseline),
            "zero": {"mean_bps": 0.0},
        },
        "subperiods": {},
        "shock_directions": {},
    }
    year = pd.Timestamp(PHASES[phase]["start"]).year
    split = min(start + pd.DateOffset(months=6), end)
    subperiods = [(f"{year}H1", start, split)]
    if split < end:
        subperiods.append((f"{year}H2", split, end))
    for label, sub_start, sub_end in subperiods:
        subset = primary_events[(primary_events.index >= sub_start) & (primary_events.index < sub_end)]
        result["subperiods"][label] = cluster_summary(subset)
    for label, sign in [("positive_btc_shock", 1), ("negative_btc_shock", -1)]:
        direction_index = events[np.sign(btc_returns.loc[events]).to_numpy() == sign]
        subset = primary_events[primary_events.index.isin(direction_index)]
        result["shock_directions"][label] = cluster_summary(subset)

    detail = {
        "events": events,
        "primary_events": primary_events,
        "used_assets": used_assets,
        "available_assets": available_assets,
        "response": response,
        "underreaction": underreaction,
        "residual": residual,
        "gap": gap,
    }
    return result, detail


def per_asset_results(
    detail: dict[str, Any],
    matrices: dict[str, pd.DataFrame],
    phase: str,
) -> list[dict[str, Any]]:
    events: pd.DatetimeIndex = detail["events"]
    response: pd.DataFrame = detail["response"]
    underreaction: pd.DataFrame = detail["underreaction"]
    start = pd.Timestamp(PHASES[phase]["start"], tz="UTC")
    end = pd.Timestamp(PHASES[phase]["end"], tz="UTC")
    p_values: list[float] = []
    rows: list[dict[str, Any]] = []
    for symbol in ALTS:
        series = response.loc[events, symbol].where(underreaction.loc[events, symbol]).dropna()
        stats = cluster_summary(series)
        p_value = stats["p_value_two_sided"]
        p_values.append(1.0 if p_value is None else float(p_value))
        quote = matrices["quote_volume"].loc[start:end, symbol]
        rows.append(
            {
                "symbol": symbol,
                **stats,
                "mean_5m_quote_volume_usdt": float(quote.mean()),
                "median_5m_quote_volume_usdt": float(quote.median()),
            }
        )
    reject, q_values, _, _ = multipletests(p_values, alpha=0.05, method="fdr_by")
    for row, rejected, q_value in zip(rows, reject, q_values, strict=True):
        row["by_fdr_q_value"] = float(q_value)
        row["significant_by_fdr_0_05"] = bool(rejected)
    return sorted(rows, key=lambda item: item["symbol"])


def development_gate(result: dict[str, Any]) -> dict[str, Any]:
    primary = result["primary"]
    baseline = result["baselines"]
    half_means = [item["mean_bps"] for item in result["subperiods"].values()]
    direction_stats = list(result["shock_directions"].values())
    checks = {
        "minimum_events": result["event_count_with_underreaction"] >= 300,
        "minimum_mean_available_assets": (
            result["mean_available_assets_per_event"] is not None
            and result["mean_available_assets_per_event"] >= 8
        ),
        "primary_mean_positive": (
            primary["mean_bps"] is not None and primary["mean_bps"] > 0
        ),
        "primary_ci_low_positive": (
            primary["ci_low_bps"] is not None and primary["ci_low_bps"] > 0
        ),
        "both_half_year_means_positive": all(
            value is not None and value > 0 for value in half_means
        ),
        "beats_btc_sign_baseline": (
            primary["mean_bps"] is not None
            and baseline["btc_sign"]["mean_bps"] is not None
            and primary["mean_bps"] > baseline["btc_sign"]["mean_bps"]
        ),
        "beats_own_sign_baseline": (
            primary["mean_bps"] is not None
            and baseline["own_return_sign"]["mean_bps"] is not None
            and primary["mean_bps"] > baseline["own_return_sign"]["mean_bps"]
        ),
        "no_direction_significantly_negative": all(
            item["ci_high_bps"] is None or item["ci_high_bps"] >= 0
            for item in direction_stats
        ),
    }
    predictive_pass = all(checks.values())
    economic_pass = primary["mean_bps"] is not None and primary["mean_bps"] >= 12
    return {
        "checks": checks,
        "predictive_pass": predictive_pass,
        "economic_relevance_for_holdout_pass": bool(economic_pass),
        "pass": bool(predictive_pass and economic_pass),
    }


def conclusion_for_phase(phase: str, gate: dict[str, Any]) -> str:
    if not gate["predictive_pass"] or not gate["economic_relevance_for_holdout_pass"]:
        return "DOES_NOT_SUPPORT"
    if phase != "confirmation":
        return "INSUFFICIENT_EVIDENCE"
    return "SUPPORTS_WITHIN_SCOPE"


def run(phase: str) -> None:
    verify_plan()
    if not prior_phase_allows(phase):
        raise RuntimeError(f"{phase} remains sealed because the prior phase did not release it")
    matrices, quality = load_matrices(phase)
    returns = np.log(matrices["close"]).diff()
    btc_returns = returns[ANCHOR]
    beta_cache = {
        days: rolling_beta(returns[ALTS], btc_returns, days) for days in [7, 30, 90]
    }
    shock_cache: dict[float, pd.DatetimeIndex] = {}
    for quantile in [0.95, 0.975, 0.99]:
        threshold = (
            btc_returns.abs()
            .rolling(SHOCK_WINDOW_BARS, min_periods=SHOCK_WINDOW_BARS)
            .quantile(quantile)
            .shift(1)
        )
        shock_cache[quantile] = select_events(
            btc_returns.abs() > threshold, COOLDOWN_BARS
        )

    config_results: list[dict[str, Any]] = []
    primary_detail: dict[str, Any] | None = None
    for config in CONFIGS:
        result, detail = analyze_config(
            config, matrices, phase, beta_cache=beta_cache, shock_cache=shock_cache
        )
        config_results.append(result)
        if config.name == "primary":
            primary_detail = detail
    assert primary_detail is not None
    primary_result = config_results[0]
    gate = development_gate(primary_result)
    release_next = bool(gate["pass"] and phase != "confirmation")
    output = {
        "phase": phase,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "study_code_sha256": code_sha256(),
        "environment": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "statsmodels": sm.__version__,
            "vectorbt": vbt.__version__,
        },
        "data_quality": quality,
        "search_disclosure": load_checkpoint()["search_disclosure"],
        "configs": config_results,
        "per_asset_primary_exploratory": per_asset_results(
            primary_detail, matrices, phase
        ),
        "gate": gate,
        "release_next_phase": release_next,
        "conclusion": conclusion_for_phase(phase, gate),
        "economic_interpretation": {
            "favorable_round_trip_proxy_bps": 12,
            "base_round_trip_proxy_bps": 32,
            "stress_round_trip_proxy_bps": 52,
            "warning": (
                "These are comparison floors, not simulated fills. Kline prediction does not "
                "include spread, depth, partial fills, funding, mark price, liquidation, or tax."
            ),
        },
    }
    output_path = STUDY_DIR / f"{phase}.json"
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    latest_path = DATA_ROOT / f"{phase}_latest.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": phase,
                "output": str(output_path),
                "conclusion": output["conclusion"],
                "release_next_phase": release_next,
                "primary": primary_result["primary"],
                "gate": gate,
            },
            indent=2,
        )
    )


def synthetic_self_test() -> None:
    rng = np.random.default_rng(20260721)
    index = pd.date_range("2023-01-01", periods=100_000, freq="5min", tz="UTC")
    btc_returns = pd.Series(rng.normal(0, 0.001, len(index)), index=index)
    alt_returns = pd.DataFrame(
        {
            symbol: 1.2 * btc_returns.to_numpy() + rng.normal(0, 0.0015, len(index))
            for symbol in ALTS
        },
        index=index,
    )
    beta = rolling_beta(alt_returns, btc_returns, 7)
    if beta.dropna().empty or not (0.8 < float(beta.dropna().median().median()) < 1.6):
        raise AssertionError("rolling beta self-test failed")
    condition = pd.Series(False, index=index)
    condition.iloc[[10, 12, 17, 18, 30]] = True
    selected = select_events(condition, cooldown_bars=6)
    expected = index[[10, 17, 30]]
    if not selected.equals(expected):
        raise AssertionError(f"cooldown self-test failed: {selected} != {expected}")
    prices = np.exp(pd.DataFrame({ANCHOR: btc_returns, **alt_returns}).cumsum()) * 100
    opens = prices.shift(1).fillna(prices.iloc[0])
    residual = future_residual(opens, prices, beta, horizon_bars=3, entry_delay_bars=1)
    if residual.shape != beta.shape:
        raise AssertionError("future residual shape self-test failed")
    sample = pd.Series(rng.normal(0.0001, 0.001, 500), index=index[:500])
    stats = cluster_summary(sample)
    if stats["n"] != 500 or stats["mean_bps"] is None:
        raise AssertionError("cluster summary self-test failed")
    print(
        json.dumps(
            {
                "status": "PASS",
                "tests": [
                    "rolling beta",
                    "event cooldown",
                    "next-open future residual alignment",
                    "cluster-robust summary",
                ],
            },
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify-plan")
    subparsers.add_parser("self-test")
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--phase", choices=PHASES, required=True)
    prepare_parser.add_argument("--workers", type=int, default=4)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--phase", choices=PHASES, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "verify-plan":
        verify_plan()
    elif args.command == "self-test":
        synthetic_self_test()
    elif args.command == "prepare":
        prepare(args.phase, args.workers)
    elif args.command == "run":
        run(args.phase)
    else:  # pragma: no cover
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
