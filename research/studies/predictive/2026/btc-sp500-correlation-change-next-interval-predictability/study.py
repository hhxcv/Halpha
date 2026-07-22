from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import math
import platform
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
from scipy.optimize import minimize
import statsmodels
import statsmodels.api as sm
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASELINE_COMMIT = "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4"
DATA_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "btc-sp500-correlation-change-next-interval-predictability/2026-07-22-v1"
)
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
BINANCE_ARCHIVE = "https://data.binance.vision/data/futures/um"
BINANCE_PUBLIC_REST = "https://fapi.binance.com/fapi/v1/klines"
DATA_START = pd.Timestamp("2019-09-01")
ARCHIVE_START = pd.Timestamp("2020-01-01")
CALIBRATION_END = pd.Timestamp("2022-08-01")
MONTHLY_ARCHIVE_END = pd.Timestamp("2026-07-01")
STAGES = {
    "development": (pd.Timestamp("2022-08-01"), pd.Timestamp("2023-11-01")),
    "evaluation": (pd.Timestamp("2023-11-01"), pd.Timestamp("2025-02-01")),
    "confirmation": (pd.Timestamp("2025-02-01"), pd.Timestamp("2026-07-18")),
}
STAGE_SEED_OFFSET = {"development": 0, "evaluation": 100_000, "confirmation": 200_000}
CONFIG = {
    "predictor_id": "RESEARCH_BTC_SP500_DCC_CHANGE_NEXT_INTERVAL_V1",
    "binance_symbol": "BTCUSDT",
    "fred_series": "SP500",
    "entry_delay_minutes": 15,
    "garch_persistence_limit": 0.999,
    "dcc_persistence_limit": 0.999,
    "hac_maxlags": 5,
    "event_low_quantile": 0.20,
    "event_high_quantile": 0.80,
    "economic_notional_fraction": 0.25,
    "stress_round_trip_underlying": 0.0052,
    "annual_full_plan_hurdle": 0.04,
    "bootstrap": {"block_observations": 10, "repetitions": 5000, "seed": 20260722},
    "minimum_calibration_rows": 650,
    "minimum_stage_rows": 300,
    "minimum_action_coverage": 0.99,
    "minimum_events_per_tail": 20,
    "minimum_event_quarters": 5,
    "download_workers": 4,
}
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
]
CONTROL_COLUMNS = [
    "delta_rho", "rho", "btc_return", "sp500_return", "btc_variance_20",
]


def now_utc() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def digest_text_normalized(path: Path) -> str:
    return digest_bytes(path.read_text(encoding="utf-8").encode("utf-8"))


def digest_value(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def stable_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in value.items() if k not in {"generated_at_utc", "content_digest"}}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    payload = dict(value)
    payload["content_digest"] = digest_value(stable_payload(payload))
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def finite(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def write_csv(path: Path, frame: pd.DataFrame) -> str:
    with path.open("w", encoding="utf-8", newline="") as handle:
        frame.to_csv(handle, index=False, lineterminator="\n")
    return digest_text_normalized(path)


def dataframe_csv_digest(frame: pd.DataFrame) -> str:
    return digest_bytes(frame.to_csv(index=False, lineterminator="\n").encode("utf-8"))


def command_checkpoint(_args: argparse.Namespace) -> None:
    frozen = ["README.md", "sources.md", "preregistration.md", "study.py"]
    payload = {
        "created_at_utc": now_utc(),
        "baseline_commit": BASELINE_COMMIT,
        "formal_strategy": {
            "id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "version": "1.0.1",
            "instrument": "BTCUSDT-PERP",
            "role": "fixed comparison context only",
        },
        "research_kind": "PREDICTIVE",
        "predictor_id": CONFIG["predictor_id"],
        "question": (
            "Does a decrease in recursively filtered BTC-SP500 conditional correlation "
            "predict a higher next actionable BTCUSDT perpetual interval return?"
        ),
        "source_sample_end": "2020-12-31",
        "source_publication": "2022-07-15",
        "replication_status": (
            "fully post-publication operational transfer with corrected asynchronous "
            "close timing; not a numerical replication"
        ),
        "calibration_end_exclusive": CALIBRATION_END.isoformat(),
        "stages": {k: [a.isoformat(), b.isoformat()] for k, (a, b) in STAGES.items()},
        "config": CONFIG,
        "data_root": str(DATA_ROOT),
        "frozen_file_sha256": {name: digest_file(HERE / name) for name in frozen},
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
            "vectorbt": vbt.__version__,
        },
        "framework_decision": (
            "SciPy/statsmodels implement the predictive econometrics; vectorbt 1.1.0 "
            "independently summarizes the frozen feasibility return series."
        ),
        "stage_open_rule": "development -> evaluation on PASS -> confirmation on PASS",
        "product_effects": "NONE",
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"content_digest": read_json(HERE / "checkpoint.json")["content_digest"]}))


def assert_checkpoint() -> dict[str, Any]:
    checkpoint = read_json(HERE / "checkpoint.json")
    checks = {
        name: digest_file(HERE / name) == expected
        for name, expected in checkpoint["frozen_file_sha256"].items()
    }
    if not all(checks.values()):
        raise RuntimeError(f"frozen identity mismatch: {checks}")
    if checkpoint["baseline_commit"] != BASELINE_COMMIT:
        raise RuntimeError("baseline identity mismatch")
    return checkpoint


def stage_authorized(stage: str) -> None:
    if stage == "evaluation":
        path = HERE / "development_gate.json"
        if not path.exists() or read_json(path)["status"] != "PASS":
            raise RuntimeError("evaluation remains sealed")
    if stage == "confirmation":
        path = HERE / "evaluation_gate.json"
        if not path.exists() or read_json(path)["status"] != "PASS":
            raise RuntimeError("confirmation remains sealed")


def fetch_url(url: str, attempts: int = 4) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Halpha-research/1.0"})
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.75 * (attempt + 1))
    raise RuntimeError(f"download failed after {attempts} attempts: {url}: {last}")


def stage_bounds(stage: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    return STAGES[stage]


def request_end(stage: str) -> pd.Timestamp:
    return stage_bounds(stage)[1] + pd.Timedelta(days=7)


def archive_specs(stage: str, interval: str) -> list[dict[str, str]]:
    start = ARCHIVE_START
    end = request_end(stage)
    months = pd.date_range(start.replace(day=1), end.replace(day=1), freq="MS")
    specs: list[dict[str, str]] = []
    for month in months:
        if month < MONTHLY_ARCHIVE_END:
            token = month.strftime("%Y-%m")
            filename = f"BTCUSDT-{interval}-{token}.zip"
            url = f"{BINANCE_ARCHIVE}/monthly/klines/BTCUSDT/{interval}/{filename}"
            specs.append({"kind": "monthly", "period": token, "interval": interval,
                          "filename": filename, "url": url})
        else:
            day_start = max(start, month)
            day_end = min(end + pd.Timedelta(days=1), month + pd.offsets.MonthBegin(1))
            for day in pd.date_range(day_start, day_end, freq="1D", inclusive="left"):
                token = day.strftime("%Y-%m-%d")
                filename = f"BTCUSDT-{interval}-{token}.zip"
                url = f"{BINANCE_ARCHIVE}/daily/klines/BTCUSDT/{interval}/{filename}"
                specs.append({"kind": "daily", "period": token, "interval": interval,
                              "filename": filename, "url": url})
    return specs


def rest_specs(interval: str) -> list[dict[str, str]]:
    interval_ms = {"1d": 86_400_000, "15m": 900_000}[interval]
    limit = 1500
    start = pd.Timestamp("2019-09-01T00:00:00Z")
    end = pd.Timestamp("2020-01-01T00:00:00Z")
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    specs: list[dict[str, str]] = []
    cursor = start_ms
    page = 0
    while cursor < end_ms:
        page_end = min(end_ms - 1, cursor + interval_ms * limit - 1)
        query = urllib.parse.urlencode({
            "symbol": CONFIG["binance_symbol"],
            "interval": interval,
            "startTime": cursor,
            "endTime": page_end,
            "limit": limit,
        })
        specs.append({
            "interval": interval,
            "page": str(page),
            "period": f"2019-warmup-{page:02d}",
            "filename": f"BTCUSDT-{interval}-2019-warmup-{page:02d}.json",
            "url": BINANCE_PUBLIC_REST + "?" + query,
        })
        cursor = page_end + 1
        page += 1
    return specs


def fetch_binance_item(stage: str, spec: dict[str, str]) -> dict[str, Any]:
    directory = DATA_ROOT / stage / "binance" / spec["interval"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / spec["filename"]
    checksum_url = spec["url"] + ".CHECKSUM"
    checksum_raw = fetch_url(checksum_url)
    upstream_sha = checksum_raw.decode("utf-8").strip().split()[0].lower()
    if len(upstream_sha) != 64:
        raise RuntimeError(f"invalid upstream checksum: {checksum_url}")
    if path.exists() and digest_file(path) == upstream_sha:
        downloaded = False
    else:
        raw = fetch_url(spec["url"])
        if digest_bytes(raw) != upstream_sha:
            raise RuntimeError(f"upstream checksum mismatch: {spec['url']}")
        partial = path.with_suffix(path.suffix + ".partial")
        partial.write_bytes(raw)
        partial.replace(path)
        downloaded = True
    checksum_path = directory / (spec["filename"] + ".CHECKSUM")
    checksum_path.write_bytes(checksum_raw)
    return {
        "source": "binance_public_archive",
        "interval": spec["interval"],
        "kind": spec["kind"],
        "period": spec["period"],
        "url": spec["url"],
        "checksum_url": checksum_url,
        "relative_path": path.relative_to(DATA_ROOT).as_posix(),
        "sha256": digest_file(path),
        "upstream_sha256": upstream_sha,
        "bytes": path.stat().st_size,
        "downloaded": downloaded,
    }


def fetch_binance_rest_item(stage: str, spec: dict[str, str]) -> dict[str, Any]:
    directory = DATA_ROOT / stage / "binance-rest" / spec["interval"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / spec["filename"]
    raw = fetch_url(spec["url"])
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise RuntimeError(f"unexpected Binance REST response: {spec['url']}")
    path.write_bytes(raw)
    return {
        "source": "binance_public_rest",
        "interval": spec["interval"],
        "kind": "bounded_rest_page",
        "period": spec["period"],
        "url": spec["url"],
        "relative_path": path.relative_to(DATA_ROOT).as_posix(),
        "sha256": digest_file(path),
        "bytes": path.stat().st_size,
    }


def command_fetch(args: argparse.Namespace) -> None:
    checkpoint = assert_checkpoint()
    stage_authorized(args.stage)
    directory = DATA_ROOT / args.stage
    directory.mkdir(parents=True, exist_ok=True)
    specs = archive_specs(args.stage, "1d") + archive_specs(args.stage, "15m")
    api_specs = rest_specs("1d") + rest_specs("15m")
    entries: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG["download_workers"]) as pool:
        futures = [pool.submit(fetch_binance_item, args.stage, spec) for spec in specs]
        for future in concurrent.futures.as_completed(futures):
            entries.append(future.result())
        api_futures = [pool.submit(fetch_binance_rest_item, args.stage, spec) for spec in api_specs]
        for future in concurrent.futures.as_completed(api_futures):
            entries.append(future.result())
    entries.sort(key=lambda row: (row["interval"], row["period"]))

    fred_end = request_end(args.stage).strftime("%Y-%m-%d")
    fred_url = FRED_CSV + "?" + urllib.parse.urlencode({
        "id": CONFIG["fred_series"],
        "cosd": DATA_START.strftime("%Y-%m-%d"),
        "coed": fred_end,
    })
    fred_raw = fetch_url(fred_url)
    fred_dir = directory / "fred"
    fred_dir.mkdir(parents=True, exist_ok=True)
    fred_path = fred_dir / f"SP500_{DATA_START.strftime('%Y-%m-%d')}_{fred_end}.csv"
    fred_path.write_bytes(fred_raw)
    entries.append({
        "source": "fred",
        "series": CONFIG["fred_series"],
        "url": fred_url,
        "relative_path": fred_path.relative_to(DATA_ROOT).as_posix(),
        "sha256": digest_file(fred_path),
        "bytes": fred_path.stat().st_size,
    })
    identity_rows = [
        {k: row[k] for k in sorted(row) if k != "downloaded"}
        for row in entries
    ]
    manifest = {
        "generated_at_utc": now_utc(),
        "stage": args.stage,
        "checkpoint_content_digest": checkpoint["content_digest"],
        "data_root": str(DATA_ROOT),
        "entries": identity_rows,
        "source_identity_digest": digest_value(identity_rows),
        "total_bytes": sum(row["bytes"] for row in entries),
        "request_boundary": {
            "start": DATA_START.isoformat(),
            "end": request_end(args.stage).isoformat(),
        },
    }
    write_json(HERE / f"source_manifest_{args.stage}.json", manifest)
    print(json.dumps({
        "stage": args.stage,
        "files": len(entries),
        "bytes": manifest["total_bytes"],
        "content_digest": read_json(HERE / f"source_manifest_{args.stage}.json")["content_digest"],
    }))


def verify_manifest(stage: str) -> dict[str, Any]:
    manifest = read_json(HERE / f"source_manifest_{stage}.json")
    failures: list[str] = []
    for row in manifest["entries"]:
        path = DATA_ROOT / row["relative_path"]
        if not path.exists():
            failures.append(f"missing:{row['relative_path']}")
            continue
        actual = digest_file(path)
        if actual != row["sha256"]:
            failures.append(f"sha256:{row['relative_path']}")
        if row["source"] == "binance_public_archive" and actual != row["upstream_sha256"]:
            failures.append(f"upstream:{row['relative_path']}")
    if failures:
        raise RuntimeError(f"source verification failed: {failures[:5]}")
    return manifest


def normalize_epoch(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    median = values.dropna().median()
    unit = "us" if median > 10**14 else "ms"
    return pd.to_datetime(values, unit=unit, utc=True, errors="coerce")


def read_kline_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise RuntimeError(f"unexpected archive members: {path}: {names}")
        raw = archive.read(names[0])
    frame = pd.read_csv(io.BytesIO(raw), header=None, names=KLINE_COLUMNS, dtype=str)
    frame["open_time"] = normalize_epoch(frame["open_time"])
    frame = frame.dropna(subset=["open_time"]).copy()
    for column in ["open", "high", "low", "close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[["open_time", "open", "high", "low", "close"]]


def read_kline_json(path: Path) -> pd.DataFrame:
    rows = json.loads(path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close"])
    frame = frame.iloc[:, :len(KLINE_COLUMNS)]
    frame.columns = KLINE_COLUMNS[:frame.shape[1]]
    frame["open_time"] = normalize_epoch(frame["open_time"])
    for column in ["open", "high", "low", "close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[["open_time", "open", "high", "low", "close"]].dropna()


def load_sources(stage: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    manifest = verify_manifest(stage)
    daily_parts: list[pd.DataFrame] = []
    intraday_parts: list[pd.DataFrame] = []
    fred: pd.DataFrame | None = None
    for row in manifest["entries"]:
        path = DATA_ROOT / row["relative_path"]
        if row["source"] == "fred":
            fred = pd.read_csv(path)
            continue
        parsed = read_kline_zip(path) if row["source"] == "binance_public_archive" else read_kline_json(path)
        if row["interval"] == "1d":
            daily_parts.append(parsed)
        elif row["interval"] == "15m":
            intraday_parts.append(parsed)
    if fred is None:
        raise RuntimeError("FRED source missing")
    daily = pd.concat(daily_parts, ignore_index=True).sort_values("open_time")
    intraday = pd.concat(intraday_parts, ignore_index=True).sort_values("open_time")
    daily = daily.drop_duplicates("open_time", keep=False).reset_index(drop=True)
    intraday = intraday.drop_duplicates("open_time", keep=False).reset_index(drop=True)
    fred["observation_date"] = pd.to_datetime(fred["observation_date"], errors="coerce")
    fred["SP500"] = pd.to_numeric(fred["SP500"], errors="coerce")
    fred = fred.dropna().sort_values("observation_date")
    if fred["observation_date"].duplicated().any():
        raise RuntimeError("duplicate FRED trading date")
    return daily, intraday, fred.reset_index(drop=True), manifest


def build_panel(daily: pd.DataFrame, intraday: pd.DataFrame, fred: pd.DataFrame) -> pd.DataFrame:
    daily_map = pd.Series(
        daily["open"].to_numpy(),
        index=daily["open_time"].dt.tz_convert("UTC").dt.normalize(),
    )
    action_map = pd.Series(intraday["open"].to_numpy(), index=intraday["open_time"])
    rows: list[dict[str, Any]] = []
    for record in fred.itertuples(index=False):
        signal_date = pd.Timestamp(record.observation_date).normalize()
        anchor_ts = (signal_date + pd.Timedelta(days=1)).tz_localize("UTC")
        action_ts = anchor_ts + pd.Timedelta(minutes=CONFIG["entry_delay_minutes"])
        rows.append({
            "signal_date": signal_date,
            "sp500_close": float(record.SP500),
            "btc_anchor": finite(daily_map.get(anchor_ts)),
            "action_time": action_ts,
            "action_price": finite(action_map.get(action_ts)),
        })
    frame = pd.DataFrame(rows).sort_values("signal_date").reset_index(drop=True)
    frame["btc_return"] = np.log(frame["btc_anchor"] / frame["btc_anchor"].shift(1))
    frame["sp500_return"] = np.log(frame["sp500_close"] / frame["sp500_close"].shift(1))
    frame["target"] = np.log(frame["action_price"].shift(-1) / frame["action_price"])
    frame["target_end_time"] = frame["action_time"].shift(-1)
    frame["hold_days"] = (
        (frame["target_end_time"] - frame["action_time"]).dt.total_seconds() / 86400.0
    )
    frame["btc_variance_20"] = frame["btc_return"].pow(2).rolling(20, min_periods=20).mean()
    return frame


def pair_transform(theta: np.ndarray, limit: float) -> tuple[float, float]:
    raw = np.exp(np.clip(np.asarray(theta, dtype=float), -20.0, 20.0))
    denominator = 1.0 + float(raw.sum())
    return limit * float(raw[0]) / denominator, limit * float(raw[1]) / denominator


def pair_inverse(first: float, second: float, limit: float) -> np.ndarray:
    gap = max(limit - first - second, 1e-8)
    return np.log(np.array([first / gap, second / gap], dtype=float))


def garch_filter(values: np.ndarray, mean: float, omega: float, alpha: float,
                 beta: float, initial_variance: float) -> tuple[np.ndarray, np.ndarray]:
    residual = np.asarray(values, dtype=float) - mean
    variance = np.empty(len(residual), dtype=float)
    variance[0] = max(float(initial_variance), 1e-10)
    for index in range(1, len(residual)):
        variance[index] = omega + alpha * residual[index - 1] ** 2 + beta * variance[index - 1]
        if not math.isfinite(variance[index]) or variance[index] <= 0:
            variance[index] = 1e-10
    standardized = residual / np.sqrt(variance)
    return variance, standardized


def fit_garch(values_decimal: np.ndarray) -> dict[str, Any]:
    values = np.asarray(values_decimal, dtype=float) * 100.0
    mean = float(np.mean(values))
    initial_variance = max(float(np.var(values, ddof=1)), 1e-6)
    limit = CONFIG["garch_persistence_limit"]

    def objective(theta: np.ndarray) -> float:
        omega = math.exp(float(np.clip(theta[0], -20.0, 20.0)))
        alpha, beta = pair_transform(theta[1:3], limit)
        variance, residual = garch_filter(values, mean, omega, alpha, beta, initial_variance)
        value = 0.5 * np.sum(np.log(variance) + residual ** 2)
        return float(value) if math.isfinite(float(value)) else 1e100

    candidates = []
    for alpha0, beta0 in [(0.05, 0.90), (0.10, 0.80), (0.02, 0.95)]:
        omega0 = max(initial_variance * (1.0 - alpha0 - beta0), 1e-6)
        start = np.r_[math.log(omega0), pair_inverse(alpha0, beta0, limit)]
        result = minimize(objective, start, method="L-BFGS-B", bounds=[(-20, 20)] * 3,
                          options={"maxiter": 2000, "ftol": 1e-12})
        candidates.append(result)
    result = min(candidates, key=lambda item: float(item.fun))
    omega = math.exp(float(np.clip(result.x[0], -20.0, 20.0)))
    alpha, beta = pair_transform(result.x[1:3], limit)
    variance, standardized = garch_filter(values, mean, omega, alpha, beta, initial_variance)
    return {
        "success": bool(result.success),
        "message": str(result.message),
        "objective": float(result.fun),
        "mean_percent": mean,
        "omega": omega,
        "alpha": alpha,
        "beta": beta,
        "persistence": alpha + beta,
        "initial_variance_percent2": initial_variance,
        "calibration_variance_percent2": variance,
        "calibration_standardized": standardized,
    }


def dcc_filter(standardized: np.ndarray, qbar: np.ndarray, first: float,
               second: float) -> tuple[np.ndarray, np.ndarray, float]:
    q = np.asarray(qbar, dtype=float).copy()
    rho_after = np.empty(len(standardized), dtype=float)
    likelihood_rho = np.empty(len(standardized), dtype=float)
    minimum_eigenvalue = math.inf
    for index, vector in enumerate(np.asarray(standardized, dtype=float)):
        diagonal = np.sqrt(np.maximum(np.diag(q), 1e-12))
        correlation = q / np.outer(diagonal, diagonal)
        eigenvalue = float(np.linalg.eigvalsh(correlation).min())
        minimum_eigenvalue = min(minimum_eigenvalue, eigenvalue)
        likelihood_rho[index] = float(correlation[0, 1])
        q = (1.0 - first - second) * qbar + first * np.outer(vector, vector) + second * q
        diagonal_after = np.sqrt(np.maximum(np.diag(q), 1e-12))
        after = q / np.outer(diagonal_after, diagonal_after)
        rho_after[index] = float(after[0, 1])
    return rho_after, likelihood_rho, minimum_eigenvalue


def fit_dcc(standardized: np.ndarray) -> dict[str, Any]:
    standardized = np.asarray(standardized, dtype=float)
    qbar = np.cov(standardized.T, ddof=1)
    limit = CONFIG["dcc_persistence_limit"]

    def objective(theta: np.ndarray) -> float:
        first, second = pair_transform(theta, limit)
        _, likelihood_rho, minimum_eigenvalue = dcc_filter(standardized, qbar, first, second)
        if minimum_eigenvalue <= 1e-10:
            return 1e100
        one_minus = np.maximum(1.0 - likelihood_rho ** 2, 1e-12)
        z1 = standardized[:, 0]
        z2 = standardized[:, 1]
        quadratic = (z1 ** 2 - 2.0 * likelihood_rho * z1 * z2 + z2 ** 2) / one_minus
        value = 0.5 * np.sum(np.log(one_minus) + quadratic)
        return float(value) if math.isfinite(float(value)) else 1e100

    candidates = []
    for first0, second0 in [(0.03, 0.90), (0.05, 0.80), (0.01, 0.97)]:
        start = pair_inverse(first0, second0, limit)
        result = minimize(objective, start, method="L-BFGS-B", bounds=[(-20, 20)] * 2,
                          options={"maxiter": 2000, "ftol": 1e-12})
        candidates.append(result)
    result = min(candidates, key=lambda item: float(item.fun))
    first, second = pair_transform(result.x, limit)
    rho_after, _, minimum_eigenvalue = dcc_filter(standardized, qbar, first, second)
    return {
        "success": bool(result.success),
        "message": str(result.message),
        "objective": float(result.fun),
        "a": first,
        "b": second,
        "persistence": first + second,
        "qbar": qbar,
        "calibration_rho_after": rho_after,
        "minimum_correlation_eigenvalue": minimum_eigenvalue,
    }


def filter_with_frozen_models(panel: pd.DataFrame, calibration_mask: pd.Series) -> tuple[pd.DataFrame, dict[str, Any]]:
    usable = panel[["btc_return", "sp500_return"]].notna().all(axis=1)
    calibration = calibration_mask & usable
    calibration_values = panel.loc[calibration, ["btc_return", "sp500_return"]].to_numpy()
    if len(calibration_values) < CONFIG["minimum_calibration_rows"]:
        raise RuntimeError(f"insufficient calibration rows: {len(calibration_values)}")
    btc_model = fit_garch(calibration_values[:, 0])
    sp500_model = fit_garch(calibration_values[:, 1])
    calibration_standardized = np.column_stack([
        btc_model["calibration_standardized"],
        sp500_model["calibration_standardized"],
    ])
    dcc_model = fit_dcc(calibration_standardized)

    full_values = panel.loc[usable, ["btc_return", "sp500_return"]].to_numpy() * 100.0
    btc_variance, btc_standardized = garch_filter(
        full_values[:, 0], btc_model["mean_percent"], btc_model["omega"],
        btc_model["alpha"], btc_model["beta"], btc_model["initial_variance_percent2"],
    )
    sp500_variance, sp500_standardized = garch_filter(
        full_values[:, 1], sp500_model["mean_percent"], sp500_model["omega"],
        sp500_model["alpha"], sp500_model["beta"], sp500_model["initial_variance_percent2"],
    )
    standardized = np.column_stack([btc_standardized, sp500_standardized])
    rho_after, _, minimum_eigenvalue = dcc_filter(
        standardized, dcc_model["qbar"], dcc_model["a"], dcc_model["b"]
    )
    output = panel.copy()
    output["rho"] = np.nan
    output.loc[usable, "rho"] = rho_after
    output["delta_rho"] = output["rho"].diff()
    output["btc_garch_variance"] = np.nan
    output.loc[usable, "btc_garch_variance"] = btc_variance / 10_000.0
    output["sp500_garch_variance"] = np.nan
    output.loc[usable, "sp500_garch_variance"] = sp500_variance / 10_000.0
    model = {
        "btc_garch": {k: finite(v) if isinstance(v, (int, float, np.floating)) else v
                       for k, v in btc_model.items()
                       if k not in {"calibration_variance_percent2", "calibration_standardized"}},
        "sp500_garch": {k: finite(v) if isinstance(v, (int, float, np.floating)) else v
                         for k, v in sp500_model.items()
                         if k not in {"calibration_variance_percent2", "calibration_standardized"}},
        "dcc": {
            "success": dcc_model["success"],
            "message": dcc_model["message"],
            "objective": finite(dcc_model["objective"]),
            "a": finite(dcc_model["a"]),
            "b": finite(dcc_model["b"]),
            "persistence": finite(dcc_model["persistence"]),
            "qbar": np.asarray(dcc_model["qbar"]).tolist(),
            "minimum_calibration_correlation_eigenvalue": finite(
                dcc_model["minimum_correlation_eigenvalue"]
            ),
            "minimum_full_correlation_eigenvalue": finite(minimum_eigenvalue),
        },
    }
    return output, model


def regression(frame: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    data = frame[["target", *columns]].dropna()
    design = sm.add_constant(data[columns], has_constant="add")
    fit = sm.OLS(data["target"], design).fit(cov_type="HAC", cov_kwds={"maxlags": CONFIG["hac_maxlags"]})
    coefficient = float(fit.params["delta_rho"])
    two_sided = float(fit.pvalues["delta_rho"])
    one_sided_negative = two_sided / 2.0 if coefficient < 0 else 1.0 - two_sided / 2.0
    return {
        "n": int(fit.nobs),
        "columns": ["const", *columns],
        "params": {key: finite(value) for key, value in fit.params.items()},
        "hac_standard_errors": {key: finite(value) for key, value in fit.bse.items()},
        "hac_two_sided_p": {key: finite(value) for key, value in fit.pvalues.items()},
        "delta_rho_coefficient": coefficient,
        "delta_rho_one_sided_negative_p": one_sided_negative,
        "r_squared": finite(fit.rsquared),
    }


def calibration_fit(frame: pd.DataFrame) -> dict[str, Any]:
    data = frame[["target", *CONTROL_COLUMNS]].dropna()
    source_design = sm.add_constant(data[["delta_rho"]], has_constant="add")
    controlled_design = sm.add_constant(data[CONTROL_COLUMNS], has_constant="add")
    source_fit = sm.OLS(data["target"], source_design).fit()
    controlled_fit = sm.OLS(data["target"], controlled_design).fit()
    return {
        "n": len(data),
        "source_params": {key: finite(value) for key, value in source_fit.params.items()},
        "controlled_params": {key: finite(value) for key, value in controlled_fit.params.items()},
        "historical_mean_target": finite(data["target"].mean()),
        "delta_rho_q20": finite(data["delta_rho"].quantile(CONFIG["event_low_quantile"])),
        "delta_rho_q80": finite(data["delta_rho"].quantile(CONFIG["event_high_quantile"])),
    }


def apply_calibration_forecast(frame: pd.DataFrame, calibration: dict[str, Any]) -> pd.Series:
    parameters = calibration["controlled_params"]
    forecast = pd.Series(float(parameters["const"]), index=frame.index, dtype=float)
    for column in CONTROL_COLUMNS:
        forecast = forecast + float(parameters[column]) * frame[column]
    return forecast


def circular_bootstrap_indices(length: int, block: int, repetitions: int,
                               seed: int) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    output: list[np.ndarray] = []
    blocks_needed = math.ceil(length / block)
    offsets = np.arange(block)
    for _ in range(repetitions):
        starts = rng.integers(0, length, size=blocks_needed)
        indices = ((starts[:, None] + offsets[None, :]) % length).reshape(-1)[:length]
        output.append(indices)
    return output


def bootstrap_metrics(frame: pd.DataFrame, stage: str) -> dict[str, list[float]]:
    target = frame["target"].to_numpy(dtype=float)
    low = frame["low_event"].to_numpy(dtype=bool)
    high = frame["high_event"].to_numpy(dtype=bool)
    plan_net = frame["plan_net"].to_numpy(dtype=float)
    hold_days = frame["hold_days"].to_numpy(dtype=float)
    spread_samples: list[float] = []
    net_daily_samples: list[float] = []
    indices_list = circular_bootstrap_indices(
        len(frame), CONFIG["bootstrap"]["block_observations"],
        CONFIG["bootstrap"]["repetitions"],
        CONFIG["bootstrap"]["seed"] + STAGE_SEED_OFFSET[stage],
    )
    for indices in indices_list:
        sampled_target = target[indices]
        sampled_low = low[indices]
        sampled_high = high[indices]
        if sampled_low.any() and sampled_high.any():
            spread_samples.append(float(sampled_target[sampled_low].mean() - sampled_target[sampled_high].mean()))
        net_daily_samples.append(float(plan_net[indices].sum() / hold_days[indices].sum()))
    return {"spread": spread_samples, "net_daily": net_daily_samples}


def interval_half_metric(frame: pd.DataFrame, column: str, mode: str = "mean") -> list[float]:
    midpoint = len(frame) // 2
    pieces = [frame.iloc[:midpoint], frame.iloc[midpoint:]]
    output: list[float] = []
    for piece in pieces:
        if mode == "daily":
            output.append(float(piece[column].sum() / piece["hold_days"].sum()))
        else:
            output.append(float(piece[column].mean()))
    return output


def vectorbt_endpoint_statistics(frame: pd.DataFrame) -> dict[str, Any]:
    capital = np.cumprod(1.0 + frame["plan_net"].to_numpy(dtype=float))
    dates = pd.DatetimeIndex(frame["target_end_time"]).tz_convert("UTC").normalize()
    values = pd.Series(capital, index=dates).groupby(level=0).last()
    initial_date = pd.Timestamp(frame["action_time"].iloc[0]).tz_convert("UTC").normalize()
    values = pd.concat([pd.Series([1.0], index=pd.DatetimeIndex([initial_date])), values])
    values = values[~values.index.duplicated(keep="last")].sort_index()
    daily_values = values.reindex(pd.date_range(values.index.min(), values.index.max(), freq="1D", tz="UTC")).ffill()
    returns = daily_values.pct_change().fillna(0.0)
    accessor = returns.vbt.returns(freq="1D")
    return {
        "endpoint_only": True,
        "total_return": finite(accessor.total()),
        "annualized_volatility": finite(accessor.annualized_volatility()),
        "sharpe_ratio_zero_rf": finite(accessor.sharpe_ratio(risk_free=0.0)),
        "max_drawdown": finite(accessor.max_drawdown()),
        "daily_observations": len(returns),
    }


def stage_expected_rows(panel: pd.DataFrame, stage: str) -> int:
    start, end = stage_bounds(stage)
    mask = (panel["signal_date"] >= start) & (panel["signal_date"] < end)
    return int(mask.sum())


def prepare(stage: str) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any], dict[str, Any]]:
    daily, intraday, fred, manifest = load_sources(stage)
    panel = build_panel(daily, intraday, fred)
    calibration_mask = panel["signal_date"] < CALIBRATION_END
    panel, model = filter_with_frozen_models(panel, calibration_mask)
    calibration_rows = panel.loc[calibration_mask].copy()
    calibration = calibration_fit(calibration_rows)
    panel["forecast"] = apply_calibration_forecast(panel, calibration)
    panel["low_event"] = panel["delta_rho"] <= calibration["delta_rho_q20"]
    panel["high_event"] = panel["delta_rho"] >= calibration["delta_rho_q80"]
    panel["direction"] = np.where(panel["low_event"], 1.0, np.where(panel["high_event"], -1.0, 0.0))
    panel["signed_gross"] = panel["direction"] * panel["target"]
    event = panel["direction"].ne(0.0).astype(float)
    panel["plan_net"] = (
        CONFIG["economic_notional_fraction"]
        * event
        * (panel["signed_gross"] - CONFIG["stress_round_trip_underlying"])
        - CONFIG["annual_full_plan_hurdle"] * panel["hold_days"] / 365.0
    )
    return panel, model, calibration, manifest


def quality_payload(stage: str) -> dict[str, Any]:
    daily, intraday, fred, manifest = load_sources(stage)
    daily_raw_count = len(daily)
    intraday_raw_count = len(intraday)
    panel = build_panel(daily, intraday, fred)
    calibration_mask = panel["signal_date"] < CALIBRATION_END
    modeled, model = filter_with_frozen_models(panel, calibration_mask)
    calibration = calibration_fit(modeled.loc[calibration_mask])
    start, end = stage_bounds(stage)
    expected = stage_expected_rows(modeled, stage)
    stage_mask = (modeled["signal_date"] >= start) & (modeled["signal_date"] < end)
    required = ["target", "target_end_time", "hold_days", *CONTROL_COLUMNS]
    eligible = modeled.loc[stage_mask].dropna(subset=required).copy()
    eligible["low_event"] = eligible["delta_rho"] <= calibration["delta_rho_q20"]
    eligible["high_event"] = eligible["delta_rho"] >= calibration["delta_rho_q80"]
    event_quarters = eligible.loc[eligible["low_event"] | eligible["high_event"], "signal_date"].dt.to_period("Q").nunique()
    price_columns_valid = bool(
        (daily[["open", "high", "low", "close"]] > 0).all().all()
        and (intraday[["open", "high", "low", "close"]] > 0).all().all()
        and (fred["SP500"] > 0).all()
    )
    ohlc_valid = bool(
        (daily["high"] >= daily[["open", "close", "low"]].max(axis=1)).all()
        and (daily["low"] <= daily[["open", "close", "high"]].min(axis=1)).all()
        and (intraday["high"] >= intraday[["open", "close", "low"]].max(axis=1)).all()
        and (intraday["low"] <= intraday[["open", "close", "high"]].min(axis=1)).all()
    )
    daily_on_grid = bool((daily["open_time"].dt.hour.eq(0) & daily["open_time"].dt.minute.eq(0)).all())
    intraday_on_grid = bool(intraday["open_time"].dt.minute.mod(15).eq(0).all())
    checks = {
        "manifest_verified": True,
        "positive_prices": price_columns_valid,
        "valid_ohlc": ohlc_valid,
        "daily_on_grid": daily_on_grid,
        "intraday_on_grid": intraday_on_grid,
        "calibration_rows": int(calibration["n"]) >= CONFIG["minimum_calibration_rows"],
        "stage_rows": len(eligible) >= CONFIG["minimum_stage_rows"],
        "action_coverage": len(eligible) / expected >= CONFIG["minimum_action_coverage"],
        "btc_garch_converged": bool(model["btc_garch"]["success"]),
        "sp500_garch_converged": bool(model["sp500_garch"]["success"]),
        "dcc_converged": bool(model["dcc"]["success"]),
        "garch_stationary": (
            model["btc_garch"]["persistence"] < CONFIG["garch_persistence_limit"]
            and model["sp500_garch"]["persistence"] < CONFIG["garch_persistence_limit"]
        ),
        "dcc_stationary": model["dcc"]["persistence"] < CONFIG["dcc_persistence_limit"],
        "positive_definite": model["dcc"]["minimum_full_correlation_eigenvalue"] > 0,
        "low_events": int(eligible["low_event"].sum()) >= CONFIG["minimum_events_per_tail"],
        "high_events": int(eligible["high_event"].sum()) >= CONFIG["minimum_events_per_tail"],
        "event_quarters": int(event_quarters) >= CONFIG["minimum_event_quarters"],
    }
    return {
        "generated_at_utc": now_utc(),
        "stage": stage,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "counts": {
            "daily_rows": daily_raw_count,
            "intraday_rows": intraday_raw_count,
            "fred_rows": len(fred),
            "calibration_rows": int(calibration["n"]),
            "expected_stage_rows": expected,
            "eligible_stage_rows": len(eligible),
            "low_events": int(eligible["low_event"].sum()),
            "high_events": int(eligible["high_event"].sum()),
            "event_quarters": int(event_quarters),
        },
        "action_coverage": finite(len(eligible) / expected),
        "model": model,
        "manifest_content_digest": manifest["content_digest"],
        "source_identity_digest": manifest["source_identity_digest"],
    }


def command_inspect(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    payload = quality_payload(args.stage)
    write_json(HERE / f"data_quality_{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage,
        "status": payload["status"],
        "eligible": payload["counts"]["eligible_stage_rows"],
        "content_digest": read_json(HERE / f"data_quality_{args.stage}.json")["content_digest"],
    }))


def quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"lower_2p5": None, "median": None, "upper_97p5": None}
    array = np.asarray(values, dtype=float)
    return {
        "lower_2p5": finite(np.quantile(array, 0.025)),
        "median": finite(np.quantile(array, 0.50)),
        "upper_97p5": finite(np.quantile(array, 0.975)),
    }


def compute_analysis(stage: str, data_quality: dict[str, Any] | None = None) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    panel, model, calibration, manifest = prepare(stage)
    start, end = stage_bounds(stage)
    mask = (panel["signal_date"] >= start) & (panel["signal_date"] < end)
    required = [
        "target", "target_end_time", "hold_days", "forecast", "plan_net",
        *CONTROL_COLUMNS,
    ]
    stage_frame = panel.loc[mask].dropna(subset=required).copy().reset_index(drop=True)
    if len(stage_frame) < CONFIG["minimum_stage_rows"]:
        raise RuntimeError(f"insufficient eligible stage rows: {len(stage_frame)}")
    source_near = regression(stage_frame, ["delta_rho"])
    controlled = regression(stage_frame, CONTROL_COLUMNS)
    midpoint = len(stage_frame) // 2
    controlled_halves = [
        regression(stage_frame.iloc[:midpoint], CONTROL_COLUMNS),
        regression(stage_frame.iloc[midpoint:], CONTROL_COLUMNS),
    ]

    realized = stage_frame["target"].to_numpy(dtype=float)
    forecast = stage_frame["forecast"].to_numpy(dtype=float)
    sum_squared_error = float(np.sum((realized - forecast) ** 2))
    zero_error = float(np.sum(realized ** 2))
    historical = float(calibration["historical_mean_target"])
    historical_error = float(np.sum((realized - historical) ** 2))
    sign_accuracy = float(np.mean(np.sign(forecast) == np.sign(realized)))

    event_frame = stage_frame.loc[stage_frame["direction"].ne(0.0)].copy()
    low_frame = stage_frame.loc[stage_frame["low_event"]]
    high_frame = stage_frame.loc[stage_frame["high_event"]]
    low_mean = float(low_frame["target"].mean())
    high_mean = float(high_frame["target"].mean())
    spread = low_mean - high_mean
    event_gross = float(event_frame["signed_gross"].mean())
    baseline_reversal = float(
        (-np.sign(event_frame["btc_return"]) * event_frame["target"]).mean()
    )
    scheduled_long = float(event_frame["target"].mean())
    scheduled_short = -scheduled_long
    net_daily = float(stage_frame["plan_net"].sum() / stage_frame["hold_days"].sum())
    net_halves = interval_half_metric(stage_frame, "plan_net", mode="daily")
    gross_halves = interval_half_metric(event_frame, "signed_gross", mode="mean")
    bootstraps = bootstrap_metrics(stage_frame, stage)
    spread_interval = quantiles(bootstraps["spread"])
    net_interval = quantiles(bootstraps["net_daily"])

    quarter = stage_frame.assign(
        quarter=stage_frame["target_end_time"].dt.tz_convert("UTC").dt.to_period("Q").astype(str)
    ).groupby("quarter", sort=True)["plan_net"].sum()
    positive_quarter = quarter[quarter > 0]
    maximum_positive_share = (
        float(positive_quarter.max() / positive_quarter.sum())
        if len(positive_quarter) else 1.0
    )
    endpoint_stats = vectorbt_endpoint_statistics(stage_frame)

    export_columns = [
        "signal_date", "action_time", "target_end_time", "hold_days", "sp500_close",
        "btc_anchor", "action_price", "btc_return", "sp500_return", "btc_variance_20",
        "rho", "delta_rho", "target", "forecast", "low_event", "high_event",
        "direction", "signed_gross", "plan_net",
    ]
    panel_export = stage_frame[export_columns].copy()
    event_export = event_frame[export_columns].copy()
    panel_digest = dataframe_csv_digest(panel_export)
    event_digest = dataframe_csv_digest(event_export)
    if data_quality is None:
        quality_path = HERE / f"data_quality_{stage}.json"
        data_quality = read_json(quality_path) if quality_path.exists() else quality_payload(stage)

    payload = {
        "generated_at_utc": now_utc(),
        "stage": stage,
        "question_id": CONFIG["predictor_id"],
        "baseline_commit": BASELINE_COMMIT,
        "formal_comparator": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP",
        "data_quality_status": data_quality["status"],
        "data_quality_content_digest": data_quality.get("content_digest", digest_value(stable_payload(data_quality))),
        "manifest_content_digest": manifest["content_digest"],
        "source_identity_digest": manifest["source_identity_digest"],
        "stage_window": [start.isoformat(), end.isoformat()],
        "eligible_rows": len(stage_frame),
        "model": model,
        "calibration": calibration,
        "predictive": {
            "source_near": source_near,
            "controlled": controlled,
            "controlled_halves": controlled_halves,
            "frozen_forecast": {
                "sum_squared_error": finite(sum_squared_error),
                "r2_vs_zero": finite(1.0 - sum_squared_error / zero_error),
                "r2_vs_calibration_historical_mean": finite(1.0 - sum_squared_error / historical_error),
                "sign_accuracy": finite(sign_accuracy),
                "mean_forecast": finite(np.mean(forecast)),
                "mean_realized": finite(np.mean(realized)),
            },
        },
        "tails": {
            "low_count": len(low_frame),
            "high_count": len(high_frame),
            "low_target_mean": finite(low_mean),
            "high_target_mean": finite(high_mean),
            "low_minus_high_spread": finite(spread),
            "spread_bootstrap": spread_interval,
            "low_long_gross_mean": finite(low_mean),
            "high_short_gross_mean": finite(-high_mean),
            "event_signed_gross_mean": finite(event_gross),
            "event_signed_gross_halves": [finite(value) for value in gross_halves],
        },
        "baselines_on_event_rows": {
            "lagged_btc_reversal_mean": finite(baseline_reversal),
            "scheduled_long_mean": finite(scheduled_long),
            "scheduled_short_mean": finite(scheduled_short),
        },
        "feasibility": {
            "notional_fraction": CONFIG["economic_notional_fraction"],
            "round_trip_underlying": CONFIG["stress_round_trip_underlying"],
            "annual_full_plan_hurdle": CONFIG["annual_full_plan_hurdle"],
            "net_total_compounded": finite(np.prod(1.0 + stage_frame["plan_net"]) - 1.0),
            "net_mean_per_calendar_day": finite(net_daily),
            "net_mean_per_calendar_day_halves": [finite(value) for value in net_halves],
            "net_daily_bootstrap": net_interval,
            "quarter_net": {key: finite(value) for key, value in quarter.items()},
            "maximum_positive_quarter_contribution_share": finite(maximum_positive_share),
            "vectorbt_endpoint_statistics": endpoint_stats,
            "funding_status": "NOT_MODELED_PREDICTIVE_SCREEN_ONLY",
        },
        "retained_csv": {
            "panel": {"filename": f"{stage}_panel.csv", "logical_utf8_sha256": panel_digest},
            "events": {"filename": f"{stage}_events.csv", "logical_utf8_sha256": event_digest},
        },
        "product_effects": "NONE",
    }
    return payload, panel_export, event_export


def command_analyze(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    quality_path = HERE / f"data_quality_{args.stage}.json"
    if not quality_path.exists():
        raise RuntimeError("run inspect before analyze")
    data_quality = read_json(quality_path)
    if data_quality["status"] != "PASS":
        raise RuntimeError("data quality gate failed")
    payload, panel, events = compute_analysis(args.stage, data_quality)
    panel_sha = write_csv(HERE / f"{args.stage}_panel.csv", panel)
    event_sha = write_csv(HERE / f"{args.stage}_events.csv", events)
    if panel_sha != payload["retained_csv"]["panel"]["logical_utf8_sha256"]:
        raise RuntimeError("panel CSV identity mismatch")
    if event_sha != payload["retained_csv"]["events"]["logical_utf8_sha256"]:
        raise RuntimeError("event CSV identity mismatch")
    write_json(HERE / f"{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage,
        "coefficient": payload["predictive"]["controlled"]["delta_rho_coefficient"],
        "spread": payload["tails"]["low_minus_high_spread"],
        "net_daily": payload["feasibility"]["net_mean_per_calendar_day"],
        "content_digest": read_json(HERE / f"{args.stage}.json")["content_digest"],
    }))


def gate_payload(stage: str, analysis: dict[str, Any], data_quality: dict[str, Any]) -> dict[str, Any]:
    predictive = analysis["predictive"]
    tails = analysis["tails"]
    feasibility = analysis["feasibility"]
    baselines = analysis["baselines_on_event_rows"]
    event_mean = tails["event_signed_gross_mean"]
    checks = {
        "data_quality": data_quality["status"] == "PASS",
        "source_near_negative_hac": (
            predictive["source_near"]["delta_rho_coefficient"] < 0
            and predictive["source_near"]["delta_rho_one_sided_negative_p"] < 0.05
        ),
        "controlled_negative_hac": (
            predictive["controlled"]["delta_rho_coefficient"] < 0
            and predictive["controlled"]["delta_rho_one_sided_negative_p"] < 0.05
        ),
        "controlled_halves_negative": all(
            item["delta_rho_coefficient"] < 0 for item in predictive["controlled_halves"]
        ),
        "frozen_oos_r2_zero": predictive["frozen_forecast"]["r2_vs_zero"] > 0,
        "frozen_oos_r2_historical": predictive["frozen_forecast"]["r2_vs_calibration_historical_mean"] > 0,
        "forecast_sign_accuracy": predictive["frozen_forecast"]["sign_accuracy"] >= 0.52,
        "tail_spread_positive": tails["low_minus_high_spread"] > 0,
        "tail_spread_bootstrap_lower": tails["spread_bootstrap"]["lower_2p5"] > 0,
        "both_tail_directions_positive": (
            tails["low_long_gross_mean"] > 0 and tails["high_short_gross_mean"] > 0
        ),
        "net_daily_positive": feasibility["net_mean_per_calendar_day"] > 0,
        "net_daily_halves_positive": all(
            value > 0 for value in feasibility["net_mean_per_calendar_day_halves"]
        ),
        "net_daily_bootstrap_lower": feasibility["net_daily_bootstrap"]["lower_2p5"] > 0,
        "beats_lagged_btc_reversal": event_mean > baselines["lagged_btc_reversal_mean"],
        "beats_scheduled_long": event_mean > baselines["scheduled_long_mean"],
        "beats_scheduled_short": event_mean > baselines["scheduled_short_mean"],
        "quarter_concentration": feasibility["maximum_positive_quarter_contribution_share"] <= 0.50,
    }
    return {
        "generated_at_utc": now_utc(),
        "stage": stage,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "analysis_content_digest": analysis["content_digest"],
        "data_quality_content_digest": data_quality["content_digest"],
        "next_stage_status": "OPEN" if all(checks.values()) else "SEALED",
        "product_effects": "NONE",
    }


def command_gate(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    analysis = read_json(HERE / f"{args.stage}.json")
    data_quality = read_json(HERE / f"data_quality_{args.stage}.json")
    payload = gate_payload(args.stage, analysis, data_quality)
    write_json(HERE / f"{args.stage}_gate.json", payload)
    print(json.dumps({
        "stage": args.stage,
        "status": payload["status"],
        "failed": payload["failed_checks"],
        "content_digest": read_json(HERE / f"{args.stage}_gate.json")["content_digest"],
    }))


def command_conclude(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    stages: dict[str, Any] = {}
    conclusion = "CANNOT_DETERMINE"
    for stage in STAGES:
        analysis_path = HERE / f"{stage}.json"
        gate_path = HERE / f"{stage}_gate.json"
        if analysis_path.exists() and gate_path.exists():
            analysis = read_json(analysis_path)
            gate = read_json(gate_path)
            stages[stage] = {
                "status": gate["status"],
                "analysis_content_digest": analysis["content_digest"],
                "gate_content_digest": gate["content_digest"],
                "controlled_delta_rho": analysis["predictive"]["controlled"]["delta_rho_coefficient"],
                "tail_spread": analysis["tails"]["low_minus_high_spread"],
                "net_daily": analysis["feasibility"]["net_mean_per_calendar_day"],
                "failed_checks": gate["failed_checks"],
            }
    if "development" in stages:
        if stages["development"]["status"] == "FAIL":
            if stages["development"]["controlled_delta_rho"] >= 0 or stages["development"]["tail_spread"] <= 0:
                conclusion = "DOES_NOT_SUPPORT"
            else:
                conclusion = "INSUFFICIENT_EVIDENCE"
        elif "evaluation" in stages and stages["evaluation"]["status"] == "FAIL":
            if stages["evaluation"]["controlled_delta_rho"] >= 0 or stages["evaluation"]["tail_spread"] <= 0:
                conclusion = "DOES_NOT_SUPPORT"
            else:
                conclusion = "INSUFFICIENT_EVIDENCE"
        elif "confirmation" in stages:
            conclusion = (
                "SUPPORTS_WITHIN_SCOPE"
                if all(stages[name]["status"] == "PASS" for name in STAGES)
                else "INSUFFICIENT_EVIDENCE"
            )
        else:
            conclusion = "INSUFFICIENT_EVIDENCE"
    payload = {
        "generated_at_utc": now_utc(),
        "conclusion": conclusion,
        "scope": (
            "post-publication BTC-SP500 conditional-correlation-change prediction; "
            "not a qualified strategy"
        ),
        "stages": stages,
        "strategy_conversion": (
            "REQUIRES_SEPARATE_FUNDING_AWARE_STUDY"
            if conclusion == "SUPPORTS_WITHIN_SCOPE" else "PROHIBITED"
        ),
        "evaluation_status": "OBSERVED" if "evaluation" in stages else "SEALED",
        "confirmation_status": "OBSERVED" if "confirmation" in stages else "SEALED",
        "long_term_profitability_claim": "NOT_AUTHORIZED",
        "product_effects": "NONE",
    }
    write_json(HERE / "results.json", payload)
    print(json.dumps({
        "conclusion": conclusion,
        "content_digest": read_json(HERE / "results.json")["content_digest"],
    }))


def compare_stable(actual: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    actual_digest = digest_value(stable_payload(actual))
    expected_digest = expected["content_digest"]
    if actual_digest != expected_digest:
        raise RuntimeError(f"{label} recomputation mismatch: {actual_digest} != {expected_digest}")


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = assert_checkpoint()
    checks: dict[str, bool] = {"checkpoint": True}
    validated_stages: list[str] = []
    for stage in STAGES:
        analysis_path = HERE / f"{stage}.json"
        if not analysis_path.exists():
            continue
        validated_stages.append(stage)
        stored_quality = read_json(HERE / f"data_quality_{stage}.json")
        recomputed_quality = quality_payload(stage)
        compare_stable(recomputed_quality, stored_quality, f"{stage} data quality")
        checks[f"{stage}_data_quality"] = True
        stored_analysis = read_json(analysis_path)
        recomputed_analysis, panel, events = compute_analysis(stage, stored_quality)
        compare_stable(recomputed_analysis, stored_analysis, f"{stage} analysis")
        checks[f"{stage}_analysis"] = True
        panel_path = HERE / stored_analysis["retained_csv"]["panel"]["filename"]
        event_path = HERE / stored_analysis["retained_csv"]["events"]["filename"]
        checks[f"{stage}_panel_csv"] = (
            digest_text_normalized(panel_path) == dataframe_csv_digest(panel)
            == stored_analysis["retained_csv"]["panel"]["logical_utf8_sha256"]
        )
        checks[f"{stage}_event_csv"] = (
            digest_text_normalized(event_path) == dataframe_csv_digest(events)
            == stored_analysis["retained_csv"]["events"]["logical_utf8_sha256"]
        )
        stored_gate = read_json(HERE / f"{stage}_gate.json")
        recomputed_gate = gate_payload(stage, stored_analysis, stored_quality)
        compare_stable(recomputed_gate, stored_gate, f"{stage} gate")
        checks[f"{stage}_gate"] = True
    if not validated_stages:
        raise RuntimeError("no analyzed stage to validate")
    development_gate = read_json(HERE / "development_gate.json")
    if development_gate["status"] == "FAIL":
        checks["evaluation_sealed"] = not (HERE / "source_manifest_evaluation.json").exists()
        checks["confirmation_sealed"] = not (HERE / "source_manifest_confirmation.json").exists()
    results = read_json(HERE / "results.json")
    checks["conclusion_enum"] = results["conclusion"] in {
        "SUPPORTS_WITHIN_SCOPE", "DOES_NOT_SUPPORT", "INSUFFICIENT_EVIDENCE", "CANNOT_DETERMINE"
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "generated_at_utc": now_utc(),
        "status": status,
        "checks": checks,
        "validated_stages": validated_stages,
        "checkpoint_content_digest": checkpoint["content_digest"],
        "results_content_digest": results["content_digest"],
        "product_effects": "NONE",
    }
    write_json(HERE / "validation.json", payload)
    print(json.dumps({
        "status": status,
        "checks": len(checks),
        "content_digest": read_json(HERE / "validation.json")["content_digest"],
    }))


def command_selftest(_args: argparse.Namespace) -> None:
    rng = np.random.default_rng(20260722)
    observations = 900
    innovations = rng.multivariate_normal([0.0, 0.0], [[1.0, 0.25], [0.25, 1.0]], observations)
    series = np.empty_like(innovations)
    variances = np.ones_like(innovations)
    for index in range(1, observations):
        variances[index] = 0.05 + 0.08 * series[index - 1] ** 2 + 0.87 * variances[index - 1]
        series[index] = np.sqrt(variances[index]) * innovations[index]
    btc = fit_garch(series[:, 0] / 100.0)
    sp500 = fit_garch(series[:, 1] / 100.0)
    standardized = np.column_stack([btc["calibration_standardized"], sp500["calibration_standardized"]])
    dcc = fit_dcc(standardized)
    if not (btc["persistence"] < 0.999 and sp500["persistence"] < 0.999 and dcc["persistence"] < 0.999):
        raise RuntimeError("synthetic stationarity self-test failed")
    fake = pd.DataFrame({
        "plan_net": [0.001, -0.0005, 0.002],
        "action_time": pd.to_datetime(["2026-01-01T00:15Z", "2026-01-02T00:15Z", "2026-01-05T00:15Z"]),
        "target_end_time": pd.to_datetime(["2026-01-02T00:15Z", "2026-01-05T00:15Z", "2026-01-06T00:15Z"]),
    })
    stats = vectorbt_endpoint_statistics(fake)
    if stats["total_return"] is None:
        raise RuntimeError("vectorbt self-test failed")
    print(json.dumps({
        "status": "PASS",
        "btc_persistence": btc["persistence"],
        "sp500_persistence": sp500["persistence"],
        "dcc_persistence": dcc["persistence"],
        "vectorbt_total": stats["total_return"],
    }))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("selftest").set_defaults(function=command_selftest)
    subparsers.add_parser("checkpoint").set_defaults(function=command_checkpoint)
    for name, function in [
        ("fetch", command_fetch),
        ("inspect", command_inspect),
        ("analyze", command_analyze),
        ("gate", command_gate),
    ]:
        child = subparsers.add_parser(name)
        child.add_argument("--stage", required=True, choices=list(STAGES))
        child.set_defaults(function=function)
    subparsers.add_parser("conclude").set_defaults(function=command_conclude)
    subparsers.add_parser("validate").set_defaults(function=command_validate)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
