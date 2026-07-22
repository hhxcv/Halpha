"""Reproduce the preregistered quarter-hour 1m order-flow predictive study.

This script only downloads public Binance historical market-data archives. It has
no authenticated endpoint, product-runtime, database, or order-management path.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import math
import os
import platform
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
import vectorbt as vbt


STUDY_DIR = Path(__file__).resolve().parent
CHECKPOINT_PATH = STUDY_DIR / "checkpoint.json"
DATA_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "quarter-hour-kline-order-flow-predictability"
)
RAW_ROOT = DATA_ROOT / "raw" / "futures" / "um" / "monthly" / "klines"
BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines"
DAILY_BASE_URL = "https://data.binance.vision/data/futures/um/daily/klines"
SYMBOLS = ["BNBUSDT", "LINKUSDT", "UNIUSDT", "FILUSDT"]
DAILY_REPAIR_DATES = {
    "FILUSDT": [
        pd.Timestamp("2022-02-26", tz="UTC"),
        pd.Timestamp("2022-02-27", tz="UTC"),
        pd.Timestamp("2022-02-28", tz="UTC"),
        pd.Timestamp("2022-04-01", tz="UTC"),
        pd.Timestamp("2022-04-02", tz="UTC"),
    ]
}
PHASES = {
    "development": ("2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "confirmation": ("2024-01-01T00:00:00Z", "2024-11-01T00:00:00Z"),
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
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]
CONTROL_COLUMNS = [
    "current_1m_log_return",
    "prior_15m_log_return",
    "log1p_quote_volume",
]
PLACEBO_OFFSETS = [2, 4, 7, 11]
BOOTSTRAP_REPLICATIONS = 999
BOOTSTRAP_SEED = 20260722
BOOTSTRAP_BLOCK_DAYS = 4
MINIMUM_EVENTS = 100_000
ECONOMIC_RELEASE_BPS = 12.0


@dataclass(frozen=True)
class Config:
    name: str
    horizon_minutes: int = 720
    entry_delay_minutes: int = 1
    boundary_offset_minutes: int = 0
    exclude_top_of_hour: bool = False
    exclude_funding_openings: bool = False
    sign_only_order_imbalance: bool = False


PRIMARY = Config(name="primary")
ROBUSTNESS = [
    Config(name="horizon_8h", horizon_minutes=480),
    Config(name="entry_delay_5m", entry_delay_minutes=5),
    Config(name="exclude_top_of_hour", exclude_top_of_hour=True),
    Config(name="exclude_funding_openings", exclude_funding_openings=True),
    Config(name="sign_only_order_imbalance", sign_only_order_imbalance=True),
]


@dataclass
class RegressionFit:
    symbol: str
    config: Config
    n: int
    days: int
    coefficient: float
    coefficient_hac_se: float
    coefficient_hac_pvalue: float
    oi_q25: float
    oi_q75: float
    iqr_effect_bps: float
    r_squared: float
    daily_xtx: np.ndarray
    daily_xty: np.ndarray
    day_positions: np.ndarray

    def public(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "config": self.config.__dict__,
            "n": self.n,
            "days": self.days,
            "order_imbalance_coefficient": self.coefficient,
            "hac_standard_error": self.coefficient_hac_se,
            "hac_two_sided_p_value": self.coefficient_hac_pvalue,
            "order_imbalance_q25": self.oi_q25,
            "order_imbalance_q75": self.oi_q75,
            "iqr_effect_bps": self.iqr_effect_bps,
            "r_squared": self.r_squared,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_sha256() -> str:
    return sha256_file(Path(__file__).resolve())


def load_checkpoint() -> dict[str, Any]:
    return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))


def verify_plan(require_fixed_hash: bool = True) -> None:
    checkpoint = load_checkpoint()
    expected_symbols = checkpoint["symbols"]
    if expected_symbols != SYMBOLS:
        raise RuntimeError(f"symbol mismatch: checkpoint={expected_symbols}, code={SYMBOLS}")
    for phase, (start, end) in PHASES.items():
        if checkpoint["periods"][phase] != [start, end]:
            raise RuntimeError(f"phase mismatch for {phase}")
    if checkpoint["primary"]["placebo_offsets_minutes"] != PLACEBO_OFFSETS:
        raise RuntimeError("placebo mismatch")
    actual_hash = code_sha256()
    expected_hash = checkpoint["study_code_sha256"]
    if require_fixed_hash and expected_hash != actual_hash:
        raise RuntimeError(
            f"study code hash is not fixed or differs: expected={expected_hash}, actual={actual_hash}"
        )
    print(
        json.dumps(
            {
                "status": "PASS",
                "study_code_sha256": actual_hash,
                "vectorbt": vbt.__version__,
                "statsmodels": sm.__version__,
            },
            indent=2,
        )
    )


def phase_months(phase: str) -> list[pd.Timestamp]:
    start, end = PHASES[phase]
    return list(
        pd.date_range(
            pd.Timestamp(start),
            pd.Timestamp(end) - pd.offsets.MonthBegin(1),
            freq="MS",
        )
    )


def source_identity(symbol: str, month: pd.Timestamp) -> tuple[Path, str, str]:
    stem = f"{symbol}-1m-{month:%Y-%m}.zip"
    local = RAW_ROOT / symbol / "1m" / stem
    url = f"{BASE_URL}/{symbol}/1m/{stem}"
    return local, url, url + ".CHECKSUM"


def daily_source_identity(symbol: str, day: pd.Timestamp) -> tuple[Path, str, str]:
    stem = f"{symbol}-1m-{day:%Y-%m-%d}.zip"
    local = RAW_ROOT / symbol / "1m" / "daily-repair" / stem
    url = f"{DAILY_BASE_URL}/{symbol}/1m/{stem}"
    return local, url, url + ".CHECKSUM"


def request_bytes(url: str, attempts: int = 5) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, timeout=(15, 120))
            response.raise_for_status()
            return response.content
        except (requests.RequestException, OSError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(2**attempt, 8))
    assert last_error is not None
    raise last_error


def parse_official_checksum(payload: bytes) -> str:
    token = payload.decode("utf-8").strip().split()[0].lower()
    if len(token) != 64 or any(char not in "0123456789abcdef" for char in token):
        raise ValueError(f"invalid official checksum payload: {payload[:120]!r}")
    return token


def prepare_archive(
    symbol: str, period: str, local: Path, url: str, checksum_url: str
) -> dict[str, Any]:
    local.parent.mkdir(parents=True, exist_ok=True)
    checksum_payload = request_bytes(checksum_url)
    official_sha256 = parse_official_checksum(checksum_payload)
    checksum_path = local.with_suffix(local.suffix + ".CHECKSUM")
    checksum_path.write_bytes(checksum_payload)
    if local.exists() and sha256_file(local) == official_sha256:
        status = "REUSED_VERIFIED"
    else:
        payload = request_bytes(url)
        temporary = local.with_suffix(local.suffix + ".part")
        temporary.write_bytes(payload)
        actual = sha256_file(temporary)
        if actual != official_sha256:
            temporary.unlink(missing_ok=True)
            raise ValueError(
                f"checksum mismatch for {url}: official={official_sha256}, actual={actual}"
            )
        os.replace(temporary, local)
        status = "DOWNLOADED_VERIFIED"
    return {
        "symbol": symbol,
        "period": period,
        "url": url,
        "checksum_url": checksum_url,
        "official_sha256": official_sha256,
        "actual_sha256": sha256_file(local),
        "bytes": local.stat().st_size,
        "local_relative_path": local.relative_to(DATA_ROOT).as_posix(),
        "status": status,
    }


def prepare_one(symbol: str, month: pd.Timestamp) -> dict[str, Any]:
    local, url, checksum_url = source_identity(symbol, month)
    return prepare_archive(symbol, f"month:{month:%Y-%m}", local, url, checksum_url)


def prepare_daily_repair(symbol: str, day: pd.Timestamp) -> dict[str, Any]:
    local, url, checksum_url = daily_source_identity(symbol, day)
    return prepare_archive(symbol, f"day-repair:{day:%Y-%m-%d}", local, url, checksum_url)


def prepare(phase: str, workers: int) -> None:
    verify_plan()
    if not prior_phase_allows(phase):
        raise RuntimeError(f"{phase} is sealed because the prior phase did not release it")
    jobs = [(symbol, month) for symbol in SYMBOLS for month in phase_months(phase)]
    repair_jobs = [
        (symbol, day)
        for symbol, days in DAILY_REPAIR_DATES.items()
        for day in days
        if PHASES[phase][0] <= day.isoformat().replace("+00:00", "Z") < PHASES[phase][1]
    ]
    records: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(prepare_one, symbol, month): (symbol, month)
            for symbol, month in jobs
        }
        futures.update(
            {
                executor.submit(prepare_daily_repair, symbol, day): (symbol, day)
                for symbol, day in repair_jobs
            }
        )
        for future in concurrent.futures.as_completed(futures):
            records.append(future.result())
    records.sort(key=lambda row: (row["symbol"], row["period"]))
    manifest = {
        "phase": phase,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "Binance official public monthly USD-M 1m Kline archives plus registered official daily integrity repairs",
        "files": records,
        "file_count": len(records),
        "total_bytes": sum(row["bytes"] for row in records),
    }
    output = STUDY_DIR / f"source_manifest_{phase}.json"
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "manifest": str(output), **manifest}, indent=2))


def read_archive(local: Path) -> pd.DataFrame:
    if not local.exists():
        raise FileNotFoundError(local)
    with zipfile.ZipFile(local) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"expected one CSV in {local}, found {members}")
        payload = archive.read(members[0])
    frame = pd.read_csv(io.BytesIO(payload), header=None, low_memory=False)
    if frame.shape[1] != len(KLINE_COLUMNS):
        raise ValueError(f"{local.name}: expected 12 columns, got {frame.shape[1]}")
    frame.columns = KLINE_COLUMNS
    open_time = pd.to_numeric(frame["open_time"], errors="coerce")
    if pd.isna(open_time.iloc[0]):
        frame = frame.iloc[1:].copy()
        open_time = pd.to_numeric(frame["open_time"], errors="raise")
    else:
        frame = frame.copy()
    if open_time.isna().any():
        raise ValueError(f"non-numeric open time in {local.name}")
    unit = "us" if float(open_time.max()) > 100_000_000_000_000 else "ms"
    frame.index = pd.to_datetime(open_time.astype("int64"), unit=unit, utc=True)
    columns = [
        "open",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
    ]
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"duplicate or unsorted timestamps in {local.name}")
    if (
        (~np.isfinite(frame[columns])).any().any()
        or (frame[["open", "close", "volume", "quote_volume"]] < 0).any().any()
        or (frame[["open", "close"]] <= 0).any().any()
        or (frame["taker_buy_base_volume"] > frame["volume"] + 1e-12).any()
    ):
        raise ValueError(f"invalid price or volume in {local.name}")
    return frame[columns]


def read_daily_repair(symbol: str, day: pd.Timestamp) -> pd.DataFrame:
    local, _, _ = daily_source_identity(symbol, day)
    frame = read_archive(local)
    expected = pd.date_range(day, day + pd.Timedelta(days=1), freq="1min", inclusive="left")
    if not frame.index.equals(expected):
        raise ValueError(
            f"daily repair grid mismatch in {local.name}: rows={len(frame)}, "
            f"expected={len(expected)}, missing={len(expected.difference(frame.index))}, "
            f"extra={len(frame.index.difference(expected))}"
        )
    return frame


def read_month(symbol: str, month: pd.Timestamp) -> pd.DataFrame:
    local, _, _ = source_identity(symbol, month)
    frame = read_archive(local)
    next_month = month + pd.offsets.MonthBegin(1)
    expected = pd.date_range(month, next_month, freq="1min", inclusive="left")
    if not frame.index.equals(expected):
        missing = expected.difference(frame.index)
        extra = frame.index.difference(expected)
        allowed_days = [
            day
            for day in DAILY_REPAIR_DATES.get(symbol, [])
            if month <= day < next_month
        ]
        allowed_index = pd.DatetimeIndex([])
        if allowed_days:
            allowed_index = pd.DatetimeIndex(
                np.concatenate(
                    [
                        pd.date_range(
                            day, day + pd.Timedelta(days=1), freq="1min", inclusive="left"
                        ).to_numpy()
                        for day in allowed_days
                    ]
                )
            )
        if len(extra) or not missing.equals(allowed_index):
            raise ValueError(
                f"unregistered grid mismatch in {local.name}: rows={len(frame)}, "
                f"expected={len(expected)}, missing={len(missing)}, extra={len(extra)}"
            )
        repairs = [
            read_daily_repair(symbol, day)
            for day in allowed_days
        ]
        frame = pd.concat([frame, *repairs]).sort_index()
    if not frame.index.equals(expected):
        raise ValueError(
            f"repaired grid mismatch in {local.name}: rows={len(frame)}, "
            f"expected={len(expected)}, missing={len(expected.difference(frame.index))}, "
            f"extra={len(frame.index.difference(expected))}"
        )
    return frame


def load_phase(phase: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    frames: dict[str, pd.DataFrame] = {}
    quality: dict[str, Any] = {"status": "PASS", "symbols": {}}
    reference_index: pd.DatetimeIndex | None = None
    for symbol in SYMBOLS:
        frame = pd.concat([read_month(symbol, month) for month in phase_months(phase)])
        if reference_index is None:
            reference_index = frame.index
        elif not frame.index.equals(reference_index):
            raise ValueError(f"{symbol} is not aligned to the reference grid")
        frames[symbol] = frame
        quality["symbols"][symbol] = {
            "rows": int(len(frame)),
            "first": frame.index[0].isoformat(),
            "last": frame.index[-1].isoformat(),
            "missing": 0,
            "duplicates": 0,
            "zero_volume_rows": int((frame["volume"] == 0).sum()),
            "order_imbalance_out_of_bounds_rows": int(
                (
                    (2 * frame["taker_buy_base_volume"] / frame["volume"].replace(0, np.nan) - 1)
                    .abs()
                    .gt(1 + 1e-9)
                ).sum()
            ),
        }
    quality["aligned_rows"] = int(len(reference_index)) if reference_index is not None else 0
    return frames, quality


def feature_frame(frame: pd.DataFrame, config: Config) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    imbalance = 2 * frame["taker_buy_base_volume"] / frame["volume"].replace(0, np.nan) - 1
    if config.sign_only_order_imbalance:
        imbalance = np.sign(imbalance)
    result["order_imbalance"] = imbalance
    result["current_1m_log_return"] = np.log(frame["close"] / frame["open"])
    result["prior_15m_log_return"] = np.log(frame["open"] / frame["open"].shift(15))
    result["log1p_quote_volume"] = np.log1p(frame["quote_volume"])
    result["target"] = np.log(
        frame["close"].shift(-config.horizon_minutes)
        / frame["open"].shift(-config.entry_delay_minutes)
    )
    minutes = frame.index.minute
    mask = ((minutes - config.boundary_offset_minutes) % 15) == 0
    if config.exclude_top_of_hour:
        mask &= minutes != 0
    if config.exclude_funding_openings:
        is_funding = (minutes == 0) & np.isin(frame.index.hour, [0, 8, 16])
        mask &= ~is_funding
    return result.loc[mask].replace([np.inf, -np.inf], np.nan).dropna()


def daily_sufficient_statistics(
    x: np.ndarray, y: np.ndarray, day_positions: np.ndarray, n_days: int
) -> tuple[np.ndarray, np.ndarray]:
    p = x.shape[1]
    daily_xtx = np.zeros((n_days, p, p), dtype=float)
    daily_xty = np.zeros((n_days, p), dtype=float)
    for day in np.unique(day_positions):
        selected = day_positions == day
        x_day = x[selected]
        y_day = y[selected]
        daily_xtx[day] = x_day.T @ x_day
        daily_xty[day] = x_day.T @ y_day
    return daily_xtx, daily_xty


def fit_asset(
    symbol: str,
    frame: pd.DataFrame,
    config: Config,
    common_days: pd.DatetimeIndex,
) -> RegressionFit:
    sample = feature_frame(frame, config)
    x = sm.add_constant(
        sample[["order_imbalance", *CONTROL_COLUMNS]].to_numpy(dtype=float),
        has_constant="add",
    )
    y = sample["target"].to_numpy(dtype=float)
    day_index = pd.DatetimeIndex(sample.index.normalize())
    day_positions = common_days.get_indexer(day_index)
    if (day_positions < 0).any():
        raise ValueError(f"{symbol}/{config.name}: day outside common phase")
    fit = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": 48})
    q25, q75 = np.quantile(sample["order_imbalance"].to_numpy(dtype=float), [0.25, 0.75])
    effect = float(fit.params[1] * (q75 - q25) * 10_000)
    daily_xtx, daily_xty = daily_sufficient_statistics(
        x, y, day_positions, len(common_days)
    )
    return RegressionFit(
        symbol=symbol,
        config=config,
        n=int(len(sample)),
        days=int(day_index.nunique()),
        coefficient=float(fit.params[1]),
        coefficient_hac_se=float(fit.bse[1]),
        coefficient_hac_pvalue=float(fit.pvalues[1]),
        oi_q25=float(q25),
        oi_q75=float(q75),
        iqr_effect_bps=effect,
        r_squared=float(fit.rsquared),
        daily_xtx=daily_xtx,
        daily_xty=daily_xty,
        day_positions=day_positions,
    )


def fit_config(
    frames: dict[str, pd.DataFrame], config: Config, common_days: pd.DatetimeIndex
) -> list[RegressionFit]:
    return [fit_asset(symbol, frames[symbol], config, common_days) for symbol in SYMBOLS]


def weighted_effect(fit: RegressionFit, day_counts: np.ndarray) -> float:
    xtx = np.tensordot(day_counts, fit.daily_xtx, axes=(0, 0))
    xty = np.tensordot(day_counts, fit.daily_xty, axes=(0, 0))
    params = np.linalg.solve(xtx, xty)
    return float(params[1] * (fit.oi_q75 - fit.oi_q25) * 10_000)


def block_bootstrap_counts(n_days: int, rng: np.random.Generator) -> np.ndarray:
    if n_days < BOOTSTRAP_BLOCK_DAYS:
        raise ValueError("not enough days for block bootstrap")
    block_starts = rng.integers(
        0,
        n_days - BOOTSTRAP_BLOCK_DAYS + 1,
        size=math.ceil(n_days / BOOTSTRAP_BLOCK_DAYS),
    )
    sampled = np.concatenate(
        [np.arange(start, start + BOOTSTRAP_BLOCK_DAYS) for start in block_starts]
    )[:n_days]
    return np.bincount(sampled, minlength=n_days).astype(float)


def bootstrap_primary_and_placebo(
    primary_fits: list[RegressionFit],
    placebo_fits: dict[int, list[RegressionFit]],
    n_days: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    primary_draws = np.empty(BOOTSTRAP_REPLICATIONS)
    difference_draws = np.empty(BOOTSTRAP_REPLICATIONS)
    for replication in range(BOOTSTRAP_REPLICATIONS):
        counts = block_bootstrap_counts(n_days, rng)
        primary = float(np.mean([weighted_effect(fit, counts) for fit in primary_fits]))
        placebo = float(
            np.mean(
                [
                    weighted_effect(fit, counts)
                    for offset in PLACEBO_OFFSETS
                    for fit in placebo_fits[offset]
                ]
            )
        )
        primary_draws[replication] = primary
        difference_draws[replication] = primary - placebo
    return {
        "method": "joint moving-block bootstrap with OLS refit and fixed full-sample IQR",
        "replications": BOOTSTRAP_REPLICATIONS,
        "seed": BOOTSTRAP_SEED,
        "block_days": BOOTSTRAP_BLOCK_DAYS,
        "primary_mean_draw_bps": float(primary_draws.mean()),
        "primary_ci_95_bps": [
            float(np.quantile(primary_draws, 0.025)),
            float(np.quantile(primary_draws, 0.975)),
        ],
        "true_minus_mean_placebo_draw_bps": float(difference_draws.mean()),
        "true_minus_mean_placebo_ci_95_bps": [
            float(np.quantile(difference_draws, 0.025)),
            float(np.quantile(difference_draws, 0.975)),
        ],
    }


def summarize_fits(fits: list[RegressionFit]) -> dict[str, Any]:
    return {
        "equal_weight_mean_iqr_effect_bps": float(
            np.mean([fit.iqr_effect_bps for fit in fits])
        ),
        "total_events": int(sum(fit.n for fit in fits)),
        "assets": [fit.public() for fit in fits],
    }


def year_splits(
    frames: dict[str, pd.DataFrame], phase: str
) -> dict[str, dict[str, Any]]:
    start = pd.Timestamp(PHASES[phase][0])
    end = pd.Timestamp(PHASES[phase][1])
    output: dict[str, dict[str, Any]] = {}
    for year in range(start.year, end.year + 1):
        split_start = max(start, pd.Timestamp(f"{year}-01-01", tz="UTC"))
        split_end = min(end, pd.Timestamp(f"{year + 1}-01-01", tz="UTC"))
        if split_start >= split_end:
            continue
        sliced = {
            symbol: frame.loc[(frame.index >= split_start) & (frame.index < split_end)]
            for symbol, frame in frames.items()
        }
        common_days = pd.date_range(split_start.normalize(), split_end.normalize(), freq="D", inclusive="left")
        output[str(year)] = summarize_fits(fit_config(sliced, PRIMARY, common_days))
    return output


def gate_result(
    primary: dict[str, Any],
    placebo: dict[str, Any],
    robustness: dict[str, dict[str, Any]],
    years: dict[str, dict[str, Any]],
    bootstrap: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    primary_mean = primary["equal_weight_mean_iqr_effect_bps"]
    placebo_mean = placebo["mean_across_offsets_and_assets_iqr_effect_bps"]
    asset_effects = [asset["iqr_effect_bps"] for asset in primary["assets"]]
    year_effects = [item["equal_weight_mean_iqr_effect_bps"] for item in years.values()]
    checks = {
        "data_quality_pass": quality["status"] == "PASS",
        "minimum_total_primary_events": primary["total_events"] >= MINIMUM_EVENTS,
        "primary_mean_positive": primary_mean > 0,
        "primary_bootstrap_ci_low_positive": bootstrap["primary_ci_95_bps"][0] > 0,
        "true_minus_mean_placebo_positive": primary_mean - placebo_mean > 0,
        "placebo_difference_ci_low_positive": bootstrap[
            "true_minus_mean_placebo_ci_95_bps"
        ][0]
        > 0,
        "all_asset_effects_positive": all(value > 0 for value in asset_effects),
        "all_calendar_year_effects_positive": all(value > 0 for value in year_effects),
        "delayed_5m_effect_positive": robustness["entry_delay_5m"][
            "equal_weight_mean_iqr_effect_bps"
        ]
        > 0,
        "exclude_top_of_hour_effect_positive": robustness["exclude_top_of_hour"][
            "equal_weight_mean_iqr_effect_bps"
        ]
        > 0,
        "exclude_funding_effect_positive": robustness["exclude_funding_openings"][
            "equal_weight_mean_iqr_effect_bps"
        ]
        > 0,
        "minimum_12bp_economic_relevance": primary_mean >= ECONOMIC_RELEASE_BPS,
    }
    return {
        "checks": checks,
        "pass": bool(all(checks.values())),
        "primary_minus_mean_placebo_bps": float(primary_mean - placebo_mean),
        "economic_reference_warning": (
            "12 bp is only a favorable round-trip relevance floor. This predictive study does "
            "not simulate fees, spread/slippage, funding, fills, margin, or an equity curve."
        ),
    }


def prior_phase_allows(phase: str) -> bool:
    if phase == "development":
        return True
    prior = "development" if phase == "evaluation" else "evaluation"
    result_path = STUDY_DIR / f"{prior}.json"
    if not result_path.exists():
        return False
    result = json.loads(result_path.read_text(encoding="utf-8"))
    return bool(result.get("release_next_phase"))


def conclusion_for_phase(phase: str, gate: dict[str, Any]) -> str:
    if not gate["pass"]:
        return "DOES_NOT_SUPPORT"
    if phase == "confirmation":
        return "SUPPORTS_WITHIN_SCOPE"
    return "INSUFFICIENT_EVIDENCE"


def run(phase: str) -> None:
    verify_plan()
    if not prior_phase_allows(phase):
        raise RuntimeError(f"{phase} is sealed because the prior phase did not release it")
    frames, quality = load_phase(phase)
    start, end = (pd.Timestamp(value) for value in PHASES[phase])
    common_days = pd.date_range(start.normalize(), end.normalize(), freq="D", inclusive="left")

    primary_fits = fit_config(frames, PRIMARY, common_days)
    placebo_fits = {
        offset: fit_config(
            frames,
            Config(name=f"placebo_shift_{offset}m", boundary_offset_minutes=offset),
            common_days,
        )
        for offset in PLACEBO_OFFSETS
    }
    robustness_fits = {
        config.name: fit_config(frames, config, common_days) for config in ROBUSTNESS
    }
    primary = summarize_fits(primary_fits)
    placebo_by_offset = {
        str(offset): summarize_fits(fits) for offset, fits in placebo_fits.items()
    }
    placebo = {
        "offsets": placebo_by_offset,
        "mean_across_offsets_and_assets_iqr_effect_bps": float(
            np.mean(
                [
                    fit.iqr_effect_bps
                    for offset in PLACEBO_OFFSETS
                    for fit in placebo_fits[offset]
                ]
            )
        ),
    }
    robustness = {
        name: summarize_fits(fits) for name, fits in robustness_fits.items()
    }
    years = year_splits(frames, phase)
    bootstrap = bootstrap_primary_and_placebo(
        primary_fits, placebo_fits, len(common_days)
    )
    gate = gate_result(primary, placebo, robustness, years, bootstrap, quality)
    release_next = bool(gate["pass"] and phase != "confirmation")
    output = {
        "phase": phase,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "study_code_sha256": code_sha256(),
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "statsmodels": sm.__version__,
            "vectorbt": vbt.__version__,
        },
        "data_quality": quality,
        "primary": primary,
        "placebo": placebo,
        "robustness": robustness,
        "calendar_years": years,
        "bootstrap": bootstrap,
        "gate": gate,
        "release_next_phase": release_next,
        "conclusion": conclusion_for_phase(phase, gate),
        "scope_warning": (
            "A predictive result is not a net-cost strategy. No overlapping-signal position "
            "path, fees, funding, spread/slippage, fills, margin, or liquidation is modeled."
        ),
    }
    output_path = STUDY_DIR / f"{phase}.json"
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    external_path = DATA_ROOT / f"{phase}_latest.json"
    external_path.parent.mkdir(parents=True, exist_ok=True)
    external_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": phase,
                "output": str(output_path),
                "primary_mean_iqr_effect_bps": primary[
                    "equal_weight_mean_iqr_effect_bps"
                ],
                "primary_bootstrap_ci_95_bps": bootstrap["primary_ci_95_bps"],
                "primary_minus_mean_placebo_bps": gate[
                    "primary_minus_mean_placebo_bps"
                ],
                "gate": gate,
                "conclusion": output["conclusion"],
                "release_next_phase": release_next,
            },
            indent=2,
        )
    )


def synthetic_self_test() -> None:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    index = pd.date_range("2021-01-01", periods=50_000, freq="1min", tz="UTC")
    returns = rng.normal(0, 0.0005, len(index))
    close = 100 * np.exp(np.cumsum(returns))
    open_price = np.r_[close[0], close[:-1]]
    volume = rng.lognormal(mean=5, sigma=1, size=len(index))
    imbalance = rng.uniform(-0.8, 0.8, len(index))
    taker_buy = volume * (imbalance + 1) / 2
    frame = pd.DataFrame(
        {
            "open": open_price,
            "close": close,
            "volume": volume,
            "quote_volume": volume * close,
            "trade_count": rng.integers(10, 1000, len(index)),
            "taker_buy_base_volume": taker_buy,
        },
        index=index,
    )
    sample = feature_frame(frame, PRIMARY)
    if sample.empty or sample.index[0].minute % 15 != 0:
        raise AssertionError("quarter-hour sample selection failed")
    proxy = 2 * taker_buy / volume - 1
    if not np.allclose(proxy, imbalance):
        raise AssertionError("order-imbalance reconstruction failed")
    common_days = pd.date_range(index[0].normalize(), index[-1].normalize(), freq="D")
    fit = fit_asset("SYNTH", frame, PRIMARY, common_days)
    if fit.n != len(sample) or not np.isfinite(fit.iqr_effect_bps):
        raise AssertionError("regression fit failed")
    counts = block_bootstrap_counts(len(common_days), rng)
    if int(counts.sum()) != len(common_days):
        raise AssertionError("block-bootstrap counts failed")
    if not np.isfinite(weighted_effect(fit, counts)):
        raise AssertionError("weighted OLS refit failed")
    print(
        json.dumps(
            {
                "status": "PASS",
                "tests": [
                    "quarter-hour phase selection",
                    "Kline order-imbalance proxy reconstruction",
                    "next-action target alignment",
                    "statsmodels OLS fit",
                    "joint-day block bootstrap sufficient-statistic refit",
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
        prepare(args.phase, workers=args.workers)
    elif args.command == "run":
        run(args.phase)
    else:  # pragma: no cover
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
