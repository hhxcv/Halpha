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
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
from scipy.stats import spearmanr
import statsmodels
import statsmodels.api as sm


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASELINE_COMMIT = "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4"
DATA_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "relative-signed-jump-next-day-predictability/2026-07-22-v1"
)
PARENT_MANIFEST = ROOT / (
    "research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/"
    "source_manifest.json"
)
PARENT_MANIFEST_SHA256 = "07d0c80a4ea858e767960c53bc9ef5345cecc1a07fb482d9d2d87b862fb50693"
PARENT_MANIFEST_CONTENT_DIGEST = "d8cab91fb7ccdc39204aa2b783d13376b92ba0137fb3cb8e6a164cb432ed3514"
ARCHIVE_BASE = "https://data.binance.vision/data/futures/um"
SYMBOLS = [
    "1000XECUSDT", "AAVEUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT",
    "CRVUSDT", "DASHUSDT", "ENSUSDT", "ETCUSDT", "HBARUSDT",
    "KAVAUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "RUNEUSDT",
    "SNXUSDT", "SOLUSDT", "TRXUSDT", "UNIUSDT", "VETUSDT",
    "XLMUSDT", "XMRUSDT", "XRPUSDT", "ZECUSDT", "ZILUSDT",
]
STAGES = {
    "development": ("2022-03-26T00:00:00Z", "2023-07-01T00:00:00Z"),
    "evaluation": ("2023-07-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-07-20T00:00:00Z"),
}
EXPECTED_DAYS = {
    name: len(pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="1D", inclusive="left"))
    for name, (start, end) in STAGES.items()
}
RESOLUTIONS = {"primary_15m": 1, "diagnostic_30m": 2, "diagnostic_1h": 4}
CONFIG = {
    "predictor_id": "RESEARCH_RSJ15_LOW_NEXT_DAY_V1",
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "minimum_rankable": 20,
    "tail_fraction": 0.20,
    "beta_days": 84,
    "entry_delay_minutes": 15,
    "target_hours": 24,
    "stress_round_trip_underlying": 0.0052,
    "economic_notional_fraction": 0.25,
    "annual_full_plan_hurdle": 0.04,
    "bootstrap": {"block_days": 7, "repetitions": 5000, "seed": 20260722},
    "hac_maxlags": 7,
    "minimum_eligible_days": 440,
    "minimum_expected_day_fraction": 0.95,
    "minimum_symbol_source_complete_fraction": 0.90,
    "minimum_positive_spread_fraction": 0.52,
    "minimum_selected_symbols": 10,
    "minimum_positive_symbol_fraction": 0.50,
    "maximum_positive_contribution_share": 0.40,
    "maximum_abs_score_control_correlation": 0.90,
    "download_workers": 8,
}
CONTROL_COLUMNS = [
    "prior_return_1d", "realized_variance_15m", "mom14", "beta84",
    "total_vol28", "max28", "log_volume30",
]
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
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


def digest_value(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    payload = dict(value)
    payload["content_digest"] = digest_value(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def command_checkpoint(_args: argparse.Namespace) -> None:
    frozen = {
        name: digest_file(HERE / name)
        for name in ["README.md", "sources.md", "preregistration.md", "study.py"]
    }
    payload = {
        "created_at_utc": now_utc(),
        "baseline_commit": BASELINE_COMMIT,
        "formal_strategy": {
            "id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "version": "1.0.1",
            "instrument": "BTCUSDT-PERP",
            "role": "fixed comparison context; shares 15-minute bar semantics only",
        },
        "research_kind": "PREDICTIVE",
        "predictor_id": CONFIG["predictor_id"],
        "question": "Does low daily relative signed jump from closed 15-minute bars predict higher next-24-hour mature-perpetual returns?",
        "replication_status": "15-minute Binance-perpetual operational transfer; not a numerical replication of 5-minute spot evidence.",
        "source_sample_end": "2021-06-30",
        "symbols": SYMBOLS,
        "stages": STAGES,
        "expected_days": EXPECTED_DAYS,
        "resolutions": RESOLUTIONS,
        "controls": CONTROL_COLUMNS,
        "config": CONFIG,
        "data_root": str(DATA_ROOT),
        "parent_daily_manifest": {
            "path": str(PARENT_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "sha256": PARENT_MANIFEST_SHA256,
            "content_digest": PARENT_MANIFEST_CONTENT_DIGEST,
        },
        "frozen_file_sha256": frozen,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "framework_decision": "Predictive statistics use pandas/statsmodels; vectorbt and exact funding are deferred until three predictive gates pass.",
        "stage_open_rule": "development -> evaluation on PASS -> confirmation on PASS",
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"digest": read_json(HERE / "checkpoint.json")["content_digest"], "expected_days": EXPECTED_DAYS}))


def assert_checkpoint() -> None:
    checkpoint = read_json(HERE / "checkpoint.json")
    checks = {
        name: checkpoint["frozen_file_sha256"][name] == digest_file(HERE / name)
        for name in checkpoint["frozen_file_sha256"]
    }
    if not all(checks.values()):
        raise RuntimeError(f"frozen identity mismatch: {checks}")


def stage_authorized(stage: str) -> None:
    if stage == "evaluation" and read_json(HERE / "development_gate.json")["status"] != "PASS":
        raise RuntimeError("evaluation remains sealed")
    if stage == "confirmation" and read_json(HERE / "evaluation_gate.json")["status"] != "PASS":
        raise RuntimeError("confirmation remains sealed")


def parent_verified_bytes(item: dict[str, Any]) -> bytes:
    path = Path(item["path"])
    raw = path.read_bytes()
    if len(raw) != int(item["bytes"]) or digest_bytes(raw) != item["sha256"]:
        raise RuntimeError(f"parent source identity mismatch: {path}")
    return raw


def stage_bounds_for_archives(stage: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = map(pd.Timestamp, STAGES[stage])
    return start - pd.Timedelta(days=1, minutes=15), end + pd.Timedelta(days=2)


def archive_specs(stage: str) -> list[dict[str, str]]:
    start, end = stage_bounds_for_archives(stage)
    month_starts = pd.date_range(start.normalize().replace(day=1), end.normalize().replace(day=1), freq="MS")
    specs: list[dict[str, str]] = []
    for symbol in SYMBOLS:
        for month in month_starts:
            if month == pd.Timestamp("2026-07-01T00:00:00Z"):
                day_start = max(start.normalize(), month)
                day_end = min(end.normalize(), pd.Timestamp("2026-07-22T00:00:00Z"))
                for day in pd.date_range(day_start, day_end, freq="1D", inclusive="left"):
                    token = day.strftime("%Y-%m-%d")
                    filename = f"{symbol}-15m-{token}.zip"
                    url = f"{ARCHIVE_BASE}/daily/klines/{symbol}/15m/{filename}"
                    specs.append({"symbol": symbol, "kind": "daily", "period": token, "filename": filename, "url": url})
            else:
                token = month.strftime("%Y-%m")
                filename = f"{symbol}-15m-{token}.zip"
                url = f"{ARCHIVE_BASE}/monthly/klines/{symbol}/15m/{filename}"
                specs.append({"symbol": symbol, "kind": "monthly", "period": token, "filename": filename, "url": url})
    return specs


def fetch_url(url: str, attempts: int = 3) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Halpha-research/1.0"})
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"download failed after {attempts} attempts: {url}: {last}")


def download_archive(stage: str, spec: dict[str, str]) -> dict[str, Any]:
    directory = DATA_ROOT / stage / spec["symbol"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / spec["filename"]
    checksum_url = spec["url"] + ".CHECKSUM"
    checksum_raw = fetch_url(checksum_url)
    checksum_text = checksum_raw.decode("utf-8").strip()
    upstream_sha = checksum_text.split()[0].lower()
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
        **spec,
        "checksum_url": checksum_url,
        "path": str(path),
        "checksum_path": str(checksum_path),
        "bytes": path.stat().st_size,
        "sha256": digest_file(path),
        "upstream_sha256": upstream_sha,
        "downloaded_now": downloaded,
    }


def command_fetch(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    if digest_file(PARENT_MANIFEST) != PARENT_MANIFEST_SHA256:
        raise RuntimeError("parent daily manifest byte identity mismatch")
    parent = read_json(PARENT_MANIFEST)
    if parent["content_digest"] != PARENT_MANIFEST_CONTENT_DIGEST:
        raise RuntimeError("parent daily manifest content identity mismatch")
    pages = [item for item in parent["kline_pages"] if item["symbol"] in SYMBOLS]
    if len(pages) != 50:
        raise RuntimeError("parent daily page coverage mismatch")
    for item in [parent["exchange_info"], *pages]:
        parent_verified_bytes(item)
    specs = archive_specs(args.stage)
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(CONFIG["download_workers"])) as pool:
        futures = [pool.submit(download_archive, args.stage, spec) for spec in specs]
        for completed, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            results.append(future.result())
            if completed % 100 == 0:
                print(json.dumps({"progress": completed, "total": len(futures)}), flush=True)
    results.sort(key=lambda item: (item["symbol"], item["kind"], item["period"]))
    payload = {
        "fetched_at_utc": now_utc(),
        "stage": args.stage,
        "archive_bounds": [value.isoformat() for value in stage_bounds_for_archives(args.stage)],
        "official_archive_base": ARCHIVE_BASE,
        "interval": "15m",
        "archives": results,
        "archive_count": len(results),
        "archive_bytes": sum(int(item["bytes"]) for item in results),
        "downloaded_now": sum(bool(item["downloaded_now"]) for item in results),
        "upstream_checksums_verified": all(item["sha256"] == item["upstream_sha256"] for item in results),
        "parent_daily_manifest": {
            "path": str(PARENT_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "sha256": PARENT_MANIFEST_SHA256,
            "content_digest": PARENT_MANIFEST_CONTENT_DIGEST,
            "exchange_info": parent["exchange_info"],
            "kline_pages": pages,
        },
    }
    write_json(HERE / f"source_manifest_{args.stage}.json", payload)
    output = read_json(HERE / f"source_manifest_{args.stage}.json")
    print(json.dumps({
        "stage": args.stage,
        "archives": output["archive_count"],
        "bytes": output["archive_bytes"],
        "downloaded_now": output["downloaded_now"],
        "digest": output["content_digest"],
    }))


def verified_archive(item: dict[str, Any]) -> bytes:
    path = Path(item["path"])
    raw = path.read_bytes()
    if len(raw) != int(item["bytes"]) or digest_bytes(raw) != item["sha256"]:
        raise RuntimeError(f"archive identity mismatch: {path}")
    if item["sha256"] != item["upstream_sha256"]:
        raise RuntimeError(f"archive no longer matches upstream binding: {path}")
    return raw


def read_archive_frame(item: dict[str, Any]) -> pd.DataFrame:
    raw = verified_archive(item)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise RuntimeError(f"unexpected archive members: {item['path']} {names}")
        with archive.open(names[0]) as member:
            frame = pd.read_csv(member, header=None, names=KLINE_COLUMNS, dtype=str)
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="coerce")
    frame = frame[frame["open_time"].notna()].copy()
    frame["open_time"] = pd.to_datetime(frame["open_time"].astype("int64"), unit="ms", utc=True)
    for column in ["open", "high", "low", "close", "volume", "quote_volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame


def load_intraday(stage: str) -> dict[str, pd.DataFrame]:
    manifest = read_json(HERE / f"source_manifest_{stage}.json")
    if manifest["stage"] != stage or not manifest["upstream_checksums_verified"]:
        raise RuntimeError("invalid stage source manifest")
    by_symbol: dict[str, list[pd.DataFrame]] = {symbol: [] for symbol in SYMBOLS}
    for item in manifest["archives"]:
        by_symbol[item["symbol"]].append(read_archive_frame(item))
    return {
        symbol: pd.concat(parts, ignore_index=True)
        .drop_duplicates("open_time", keep="last")
        .sort_values("open_time")
        .set_index("open_time")
        for symbol, parts in by_symbol.items()
    }


def load_daily() -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    if digest_file(PARENT_MANIFEST) != PARENT_MANIFEST_SHA256:
        raise RuntimeError("parent daily manifest changed")
    parent = read_json(PARENT_MANIFEST)
    by_symbol: dict[str, list[Any]] = {symbol: [] for symbol in SYMBOLS}
    for item in parent["kline_pages"]:
        if item["symbol"] in by_symbol:
            by_symbol[item["symbol"]].extend(json.loads(parent_verified_bytes(item)))
    bars: dict[str, pd.DataFrame] = {}
    for symbol, rows in by_symbol.items():
        frame = pd.DataFrame(rows, columns=KLINE_COLUMNS)
        frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        for column in ["open", "high", "low", "close", "volume", "quote_volume"]:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        bars[symbol] = frame.drop_duplicates("open_time", keep="last").sort_values("open_time").set_index("open_time")
    exchange = json.loads(parent_verified_bytes(parent["exchange_info"]))
    return bars, exchange


def signal_source_complete(frame: pd.DataFrame, decision: pd.Timestamp) -> bool:
    day = decision - pd.Timedelta(days=1)
    expected = pd.date_range(day, decision, freq="15min", inclusive="left")
    required = expected.insert(0, day - pd.Timedelta(minutes=15))
    entry = decision + pd.Timedelta(minutes=int(CONFIG["entry_delay_minutes"]))
    exit_time = entry + pd.Timedelta(hours=int(CONFIG["target_hours"]))
    return required.isin(frame.index).all() and entry in frame.index and exit_time in frame.index


def command_inspect(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    intraday = load_intraday(args.stage)
    _daily, exchange = load_daily()
    start, end = map(pd.Timestamp, STAGES[args.stage])
    decisions = pd.date_range(start, end, freq="1D", inclusive="left")
    source_checks: dict[str, Any] = {}
    status = True
    for symbol, frame in intraday.items():
        duplicate_count = int(frame.index.duplicated().sum())
        invalid_ohlc = int(((frame[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
        invalid_range = int(((frame["high"] < frame[["open", "close"]].max(axis=1)) | (frame["low"] > frame[["open", "close"]].min(axis=1))).sum())
        complete = sum(signal_source_complete(frame, decision) for decision in decisions)
        fraction = complete / len(decisions)
        check = {
            "rows": int(len(frame)),
            "first": frame.index.min().isoformat(),
            "last": frame.index.max().isoformat(),
            "duplicates": duplicate_count,
            "invalid_ohlc": invalid_ohlc,
            "invalid_range": invalid_range,
            "complete_signal_and_target_days": int(complete),
            "complete_fraction": float(fraction),
        }
        source_checks[symbol] = check
        status = status and duplicate_count == 0 and invalid_ohlc == 0 and invalid_range == 0
        status = status and fraction >= float(CONFIG["minimum_symbol_source_complete_fraction"])
    current = {item["symbol"]: item for item in exchange["symbols"] if item["symbol"] in SYMBOLS}
    current_ok = len(current) == len(SYMBOLS) and all(
        item["status"] == "TRADING" and item["contractType"] == "PERPETUAL"
        for item in current.values()
    )
    manifest = read_json(HERE / f"source_manifest_{args.stage}.json")
    payload = {
        "checked_at_utc": now_utc(),
        "stage": args.stage,
        "status": "PASS" if status and current_ok else "FAIL",
        "expected_decision_days": len(decisions),
        "symbols": source_checks,
        "current_exchange": {"present": len(current), "all_trading_perpetual": current_ok},
        "source_manifest_digest": manifest["content_digest"],
        "archive_count": manifest["archive_count"],
        "archive_bytes": manifest["archive_bytes"],
    }
    write_json(HERE / f"data_quality_{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage,
        "status": payload["status"],
        "complete_fraction_range": [
            min(item["complete_fraction"] for item in source_checks.values()),
            max(item["complete_fraction"] for item in source_checks.values()),
        ],
    }))
    if payload["status"] != "PASS":
        raise RuntimeError("data quality failed")


def daily_return_frame(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    output = pd.DataFrame()
    for symbol in SYMBOLS:
        output[symbol] = bars[symbol]["open"].shift(-1) / bars[symbol]["open"] - 1.0
    return output


def fit_beta(asset: pd.Series, market: pd.Series) -> float:
    design = np.column_stack([np.ones(len(asset)), market.to_numpy(float)])
    return float(np.linalg.lstsq(design, asset.to_numpy(float), rcond=None)[0][1])


def compounded(values: pd.Series) -> float:
    return float(np.prod(1.0 + values.to_numpy(float)) - 1.0)


def rsj_feature(frame: pd.DataFrame, decision: pd.Timestamp, step: int) -> tuple[float, float] | None:
    day = decision - pd.Timedelta(days=1)
    expected = pd.date_range(day, decision, freq="15min", inclusive="left")
    required = expected.insert(0, day - pd.Timedelta(minutes=15))
    if not required.isin(frame.index).all():
        return None
    closes = frame.loc[required, "close"].to_numpy(float)
    sampled = np.concatenate([[closes[0]], closes[step::step]])
    returns = np.diff(np.log(sampled))
    if len(returns) != 96 // step:
        raise RuntimeError("unexpected derived resolution length")
    squares = returns * returns
    positive = float(squares[returns > 0].sum())
    negative = float(squares[returns < 0].sum())
    realized = positive + negative
    if not math.isfinite(realized) or realized <= 0:
        return None
    return (positive - negative) / realized, realized


def build_panel(
    stage: str,
    intraday: dict[str, pd.DataFrame],
    daily: dict[str, pd.DataFrame],
    step: int,
) -> pd.DataFrame:
    start, end = map(pd.Timestamp, STAGES[stage])
    decisions = pd.date_range(start, end, freq="1D", inclusive="left")
    daily_returns = daily_return_frame(daily)
    market_sum = daily_returns.sum(axis=1, min_count=len(SYMBOLS))
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        beta_dates = pd.date_range(decision - pd.Timedelta(days=int(CONFIG["beta_days"])), decision, freq="1D", inclusive="left")
        mom14_dates = pd.date_range(decision - pd.Timedelta(days=14), decision, freq="1D", inclusive="left")
        control_dates = pd.date_range(decision - pd.Timedelta(days=28), decision, freq="1D", inclusive="left")
        volume_dates = pd.date_range(decision - pd.Timedelta(days=30), decision, freq="1D", inclusive="left")
        signal_date = decision - pd.Timedelta(days=1)
        entry = decision + pd.Timedelta(minutes=int(CONFIG["entry_delay_minutes"]))
        exit_time = entry + pd.Timedelta(hours=int(CONFIG["target_hours"]))
        for symbol in SYMBOLS:
            feature = rsj_feature(intraday[symbol], decision, step)
            if feature is None or entry not in intraday[symbol].index or exit_time not in intraday[symbol].index:
                continue
            frame = daily[symbol]
            required_daily = set(beta_dates) | set(mom14_dates) | set(control_dates) | set(volume_dates) | {signal_date}
            if not required_daily.issubset(set(frame.index)):
                continue
            asset_beta = daily_returns.loc[beta_dates, symbol]
            if asset_beta.isna().any():
                continue
            loo_market = (market_sum.loc[beta_dates] - asset_beta) / (len(SYMBOLS) - 1)
            if loo_market.isna().any():
                continue
            median_volume = float(frame.loc[volume_dates, "quote_volume"].median())
            if median_volume < float(CONFIG["minimum_median_quote_volume_30d"]):
                continue
            rsj, realized = feature
            entry_price = float(intraday[symbol].at[entry, "open"])
            exit_price = float(intraday[symbol].at[exit_time, "open"])
            rows.append({
                "decision_time": decision,
                "signal_date": signal_date,
                "entry_time": entry,
                "exit_time": exit_time,
                "symbol": symbol,
                "resolution_minutes": 15 * step,
                "rsj": float(rsj),
                "realized_variance_15m": float(rsj_feature(intraday[symbol], decision, 1)[1]),
                "prior_return_1d": float(daily_returns.at[signal_date, symbol]),
                "mom14": compounded(daily_returns.loc[mom14_dates, symbol]),
                "beta84": fit_beta(asset_beta, loo_market),
                "total_vol28": float(daily_returns.loc[control_dates, symbol].std(ddof=1)),
                "max28": float(daily_returns.loc[control_dates, symbol].max()),
                "log_volume30": float(np.log(median_volume)),
                "target_return": exit_price / entry_price - 1.0,
            })
    panel = pd.DataFrame(rows)
    if panel.empty:
        return panel
    assigned: list[pd.DataFrame] = []
    for _decision, group in panel.groupby("decision_time", sort=True):
        ordered = group.sort_values(["rsj", "symbol"]).copy()
        n = len(ordered)
        if n < int(CONFIG["minimum_rankable"]):
            continue
        tail = max(1, int(math.ceil(n * float(CONFIG["tail_fraction"]))))
        ordered["group"] = "other"
        ordered.iloc[:tail, ordered.columns.get_loc("group")] = "low"
        ordered.iloc[-tail:, ordered.columns.get_loc("group")] = "high"
        assigned.append(ordered)
    return pd.concat(assigned, ignore_index=True) if assigned else pd.DataFrame()


def zscore(series: pd.Series) -> pd.Series:
    std = float(series.std(ddof=1))
    if not math.isfinite(std) or std <= 0:
        return pd.Series(0.0, index=series.index)
    return (series - float(series.mean())) / std


def block_ci(values: np.ndarray) -> list[float]:
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"]))
    block = int(CONFIG["bootstrap"]["block_days"])
    means = np.empty(int(CONFIG["bootstrap"]["repetitions"]))
    for repetition in range(len(means)):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(block)) % len(values)).tolist())
        means[repetition] = values[np.asarray(chosen[:len(values)])].mean()
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def hac_mean(values: np.ndarray, expected_positive: bool) -> dict[str, float]:
    fit = sm.OLS(np.asarray(values, dtype=float), np.ones((len(values), 1))).fit(
        cov_type="HAC", cov_kwds={"maxlags": int(CONFIG["hac_maxlags"])}
    )
    coefficient = float(fit.params[0])
    two_sided = float(fit.pvalues[0])
    favorable = coefficient >= 0 if expected_positive else coefficient <= 0
    return {
        "mean": coefficient,
        "hac_t": float(fit.tvalues[0]),
        "hac_two_sided_p": two_sided,
        "hac_one_sided_p": two_sided / 2.0 if favorable else 1.0 - two_sided / 2.0,
    }


def tail_groups(group: pd.DataFrame, column: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = group.sort_values([column, "symbol"])
    tail = max(1, int(math.ceil(len(ordered) * float(CONFIG["tail_fraction"]))))
    return ordered.head(tail), ordered.tail(tail)


def full_plan_proxy(target_return: float) -> float:
    hurdle = (1.0 + float(CONFIG["annual_full_plan_hurdle"])) ** (1.0 / 365.0) - 1.0
    return float(CONFIG["economic_notional_fraction"]) * (
        target_return - float(CONFIG["stress_round_trip_underlying"])
    ) - hurdle


def daily_statistics(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    reversal_rows: list[dict[str, Any]] = []
    for decision, group in panel.groupby("decision_time", sort=True):
        low = group[group["group"] == "low"]
        high = group[group["group"] == "high"]
        if low.empty or high.empty:
            continue
        selected = low.sort_values(["log_volume30", "symbol"], ascending=[False, True]).iloc[0]
        reversal_low, reversal_high = tail_groups(group, "prior_return_1d")
        reversal_selected = reversal_low.sort_values(["log_volume30", "symbol"], ascending=[False, True]).iloc[0]
        standardized = group.copy()
        for column in ["rsj", *CONTROL_COLUMNS]:
            standardized[column] = zscore(standardized[column])
        design = sm.add_constant(standardized[["rsj", *CONTROL_COLUMNS]].to_numpy(float))
        controlled = np.linalg.lstsq(design, standardized["target_return"].to_numpy(float), rcond=None)[0]
        correlations = {
            column: float(spearmanr(group["rsj"], group[column]).statistic)
            for column in CONTROL_COLUMNS
        }
        spread = float(low["target_return"].mean() - high["target_return"].mean())
        reversal_spread = float(reversal_low["target_return"].mean() - reversal_high["target_return"].mean())
        daily_rows.append({
            "decision_time": decision,
            "rankable": int(len(group)),
            "low_rsj_return": float(low["target_return"].mean()),
            "high_rsj_return": float(high["target_return"].mean()),
            "low_minus_high": spread,
            "reversal_low_minus_high": reversal_spread,
            "rsj_minus_reversal_spread": spread - reversal_spread,
            "rsj_rank_ic": float(spearmanr(group["rsj"], group["target_return"]).statistic),
            "controlled_rsj_slope": float(controlled[1]),
            "equal_weight_market_return": float(group["target_return"].mean()),
            **{f"score_{key}_spearman": value for key, value in correlations.items()},
            "selected_symbol": str(selected["symbol"]),
            "selected_gross_return": float(selected["target_return"]),
            "reversal_selected_symbol": str(reversal_selected["symbol"]),
            "reversal_selected_gross_return": float(reversal_selected["target_return"]),
        })
        selected_rows.append({
            "decision_time": decision,
            "entry_time": selected["entry_time"],
            "exit_time": selected["exit_time"],
            "symbol": str(selected["symbol"]),
            "gross_return": float(selected["target_return"]),
            "full_plan_after_cost_and_hurdle": full_plan_proxy(float(selected["target_return"])),
        })
        reversal_rows.append({
            "decision_time": decision,
            "entry_time": reversal_selected["entry_time"],
            "exit_time": reversal_selected["exit_time"],
            "symbol": str(reversal_selected["symbol"]),
            "gross_return": float(reversal_selected["target_return"]),
            "full_plan_after_cost_and_hurdle": full_plan_proxy(float(reversal_selected["target_return"])),
        })
    return pd.DataFrame(daily_rows), pd.DataFrame(selected_rows), pd.DataFrame(reversal_rows)


def proxy_summary(selected: pd.DataFrame) -> dict[str, Any]:
    values = selected["full_plan_after_cost_and_hurdle"].to_numpy(float)
    midpoint = len(values) // 2
    symbols = selected.groupby("symbol")["full_plan_after_cost_and_hurdle"].agg(["count", "mean", "sum"])
    positive = symbols[symbols["sum"] > 0]
    positive_total = float(positive["sum"].sum())
    maximum_share = float(positive["sum"].max() / positive_total) if positive_total > 0 else 1.0
    return {
        "mean_after_cost_and_hurdle": float(values.mean()),
        "block_bootstrap_95pct": block_ci(values),
        "positive_fraction": float((values > 0).mean()),
        "first_half_mean": float(values[:midpoint].mean()),
        "second_half_mean": float(values[midpoint:].mean()),
        "selected_symbols": int(len(symbols)),
        "positive_symbol_fraction": float((symbols["mean"] > 0).mean()),
        "maximum_positive_contribution_share": maximum_share,
    }


def summarize(panel: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily, selected, reversal_selected = daily_statistics(panel)
    spread = daily["low_minus_high"].to_numpy(float)
    midpoint = len(spread) // 2
    correlation_columns = [f"score_{column}_spearman" for column in CONTROL_COLUMNS]
    primary_proxy = proxy_summary(selected)
    reversal_proxy = proxy_summary(reversal_selected)
    summary = {
        "days": int(len(daily)),
        "panel_rows": int(len(panel)),
        "rankable": {
            "minimum": int(daily["rankable"].min()),
            "median": float(daily["rankable"].median()),
            "maximum": int(daily["rankable"].max()),
        },
        "spread": {
            "mean": float(spread.mean()),
            "block_bootstrap_95pct": block_ci(spread),
            "positive_fraction": float((spread > 0).mean()),
            "first_half_mean": float(spread[:midpoint].mean()),
            "second_half_mean": float(spread[midpoint:].mean()),
        },
        "rank_ic": hac_mean(daily["rsj_rank_ic"].to_numpy(float), expected_positive=False),
        "controlled_rsj_slope": hac_mean(daily["controlled_rsj_slope"].to_numpy(float), expected_positive=False),
        "reversal_baseline": {
            "spread_mean": float(daily["reversal_low_minus_high"].mean()),
            "rsj_minus_reversal_spread_mean": float(daily["rsj_minus_reversal_spread"].mean()),
            "proxy_mean_after_cost_and_hurdle": reversal_proxy["mean_after_cost_and_hurdle"],
            "rsj_minus_reversal_proxy_mean": primary_proxy["mean_after_cost_and_hurdle"] - reversal_proxy["mean_after_cost_and_hurdle"],
        },
        "equal_weight_market_return_mean": float(daily["equal_weight_market_return"].mean()),
        "single_leg_proxy": primary_proxy,
        "score_control_correlation": {
            "median_absolute_by_control": {
                column.replace("score_", "").replace("_spearman", ""): float(daily[column].abs().median())
                for column in correlation_columns
            },
            "maximum_median_absolute": float(max(daily[column].abs().median() for column in correlation_columns)),
        },
    }
    return summary, daily, selected, reversal_selected


def analysis_core(stage: str) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    intraday = load_intraday(stage)
    daily, _exchange = load_daily()
    summaries: dict[str, Any] = {}
    outputs: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name, step in RESOLUTIONS.items():
        panel = build_panel(stage, intraday, daily, step)
        summary, daily_stats, selected, reversal_selected = summarize(panel)
        summaries[name] = summary
        for kind, frame in [
            (f"{name}_panel", panel),
            (f"{name}_daily", daily_stats),
            (f"{name}_selected", selected),
            (f"{name}_reversal_selected", reversal_selected),
        ]:
            outputs[kind] = frame
            raw = frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ").encode("utf-8")
            hashes[f"{stage}_{kind}.csv"] = digest_bytes(raw)
    source = read_json(HERE / f"source_manifest_{stage}.json")
    quality = read_json(HERE / f"data_quality_{stage}.json")
    core = {
        "stage": stage,
        "period": {"start": STAGES[stage][0], "end_exclusive": STAGES[stage][1]},
        "source_manifest_digest": source["content_digest"],
        "data_quality_digest": quality["content_digest"],
        "summaries": summaries,
        "csv_sha256": hashes,
        "search_disclosure": {
            "selectable_primary_configurations": 1,
            "main": "15-minute RSJ; low-minus-high quintile; 15-minute delayed next-24-hour target",
            "diagnostics_only": ["30-minute RSJ", "one-hour RSJ"],
            "source_sample_ends_before_all_halpha_stages": True,
            "prior_broad_market_path_exposure": True,
        },
    }
    return core, outputs


def command_analyze(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    quality = read_json(HERE / f"data_quality_{args.stage}.json")
    if quality["status"] != "PASS":
        raise RuntimeError("data quality is not PASS")
    core, outputs = analysis_core(args.stage)
    for name, frame in outputs.items():
        (HERE / f"{args.stage}_{name}.csv").write_bytes(
            frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ").encode("utf-8")
        )
    write_json(HERE / f"{args.stage}.json", {"generated_at_utc": now_utc(), **core})
    main = core["summaries"]["primary_15m"]
    print(json.dumps({
        "stage": args.stage,
        "days": main["days"],
        "spread": main["spread"]["mean"],
        "reversal": main["reversal_baseline"]["spread_mean"],
        "proxy": main["single_leg_proxy"]["mean_after_cost_and_hurdle"],
    }))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    main = result["summaries"]["primary_15m"]
    spread = main["spread"]
    proxy = main["single_leg_proxy"]
    return {
        "data_quality_pass": read_json(HERE / f"data_quality_{stage}.json")["status"] == "PASS",
        "eligible_days_at_least_440": main["days"] >= int(CONFIG["minimum_eligible_days"]),
        "expected_day_fraction_at_least_95pct": main["days"] / EXPECTED_DAYS[stage] >= float(CONFIG["minimum_expected_day_fraction"]),
        "median_rankable_at_least_20": main["rankable"]["median"] >= int(CONFIG["minimum_rankable"]),
        "spread_mean_positive": spread["mean"] > 0,
        "spread_bootstrap_lower_positive": spread["block_bootstrap_95pct"][0] > 0,
        "spread_positive_fraction_at_least_52pct": spread["positive_fraction"] >= float(CONFIG["minimum_positive_spread_fraction"]),
        "spread_both_halves_positive": spread["first_half_mean"] > 0 and spread["second_half_mean"] > 0,
        "rank_ic_negative": main["rank_ic"]["mean"] < 0,
        "rank_ic_one_sided_hac_p_lt_5pct": main["rank_ic"]["hac_one_sided_p"] < 0.05,
        "controlled_slope_negative": main["controlled_rsj_slope"]["mean"] < 0,
        "controlled_slope_one_sided_hac_p_lt_5pct": main["controlled_rsj_slope"]["hac_one_sided_p"] < 0.05,
        "rsj_spread_exceeds_reversal": main["reversal_baseline"]["rsj_minus_reversal_spread_mean"] > 0,
        "proxy_mean_after_cost_hurdle_positive": proxy["mean_after_cost_and_hurdle"] > 0,
        "proxy_bootstrap_lower_positive": proxy["block_bootstrap_95pct"][0] > 0,
        "proxy_both_halves_positive": proxy["first_half_mean"] > 0 and proxy["second_half_mean"] > 0,
        "proxy_selected_symbol_breadth": proxy["selected_symbols"] >= int(CONFIG["minimum_selected_symbols"]),
        "proxy_positive_symbol_fraction": proxy["positive_symbol_fraction"] >= float(CONFIG["minimum_positive_symbol_fraction"]),
        "proxy_contribution_not_concentrated": proxy["maximum_positive_contribution_share"] <= float(CONFIG["maximum_positive_contribution_share"]),
        "proxy_exceeds_reversal_proxy": main["reversal_baseline"]["rsj_minus_reversal_proxy_mean"] > 0,
        "diagnostic_30m_spread_nonnegative": result["summaries"]["diagnostic_30m"]["spread"]["mean"] >= 0,
        "diagnostic_1h_spread_nonnegative": result["summaries"]["diagnostic_1h"]["spread"]["mean"] >= 0,
        "score_not_control_duplicate": main["score_control_correlation"]["maximum_median_absolute"] < float(CONFIG["maximum_abs_score_control_correlation"]),
    }


ECONOMIC_CHECKS = {"spread_mean_positive", "proxy_mean_after_cost_hurdle_positive"}


def command_gate(args: argparse.Namespace) -> None:
    result = read_json(HERE / f"{args.stage}.json")
    checks = gate_checks(args.stage, result)
    payload = {
        "generated_at_utc": now_utc(),
        "stage": args.stage,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failed_checks": [key for key, value in checks.items() if not value],
        "economic_failed_checks": [key for key in ECONOMIC_CHECKS if not checks.get(key, True)],
        "result_digest": result["content_digest"],
    }
    write_json(HERE / f"{args.stage}_gate.json", payload)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "failed": payload["failed_checks"]}))


def command_conclude(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    available = [stage for stage in STAGES if (HERE / f"{stage}.json").exists()]
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in available}
    all_pass = len(gates) == 3 and all(gate["status"] == "PASS" for gate in gates.values())
    any_economic_failure = any(gate["economic_failed_checks"] for gate in gates.values())
    conclusion = "SUPPORTS_WITHIN_SCOPE" if all_pass else ("DOES_NOT_SUPPORT" if any_economic_failure else "INSUFFICIENT_EVIDENCE")
    payload = {
        "generated_at_utc": now_utc(),
        "conclusion": conclusion,
        "claim": "Predictive 15-minute operational transfer only; no strategy qualification or long-term profitability claim",
        "available_stages": available,
        "stage_gate_status": {stage: gate["status"] for stage, gate in gates.items()},
        "stage_failed_checks": {stage: gate["failed_checks"] for stage, gate in gates.items()},
        "next_step": (
            "Open a separate actual-funding vectorbt strategy-candidate question"
            if conclusion == "SUPPORTS_WITHIN_SCOPE"
            else "No strategy conversion and no 5-minute rescue search; RSJ15 family stop remains binding"
        ),
        "product_effects": "NONE",
    }
    write_json(HERE / "results.json", payload)
    print(json.dumps({"conclusion": conclusion, "available_stages": available}))


def command_validate(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    checks: dict[str, bool] = {
        "parent_daily_manifest_identity": digest_file(PARENT_MANIFEST) == PARENT_MANIFEST_SHA256,
    }
    for stage in STAGES:
        source_path = HERE / f"source_manifest_{stage}.json"
        if not source_path.exists():
            continue
        source = read_json(source_path)
        checks[f"{stage}_all_archive_identities"] = all(
            Path(item["path"]).exists()
            and Path(item["path"]).stat().st_size == int(item["bytes"])
            and digest_file(Path(item["path"])) == item["sha256"] == item["upstream_sha256"]
            for item in source["archives"]
        )
        quality = read_json(HERE / f"data_quality_{stage}.json")
        checks[f"{stage}_data_quality_pass"] = quality["status"] == "PASS"
        result_path = HERE / f"{stage}.json"
        if result_path.exists():
            stored = read_json(result_path)
            recomputed, _ = analysis_core(stage)
            stored_core = {key: value for key, value in stored.items() if key not in {"generated_at_utc", "content_digest"}}
            checks[f"{stage}_economics_recomputed"] = digest_value(stored_core) == digest_value(recomputed)
            checks[f"{stage}_gate_bound"] = read_json(HERE / f"{stage}_gate.json")["result_digest"] == stored["content_digest"]
            for name, expected in stored["csv_sha256"].items():
                checks[f"{name}_identity"] = digest_file(HERE / name) == expected
    if (HERE / "results.json").exists():
        result = read_json(HERE / "results.json")
        checks["valid_conclusion"] = result["conclusion"] in {
            "SUPPORTS_WITHIN_SCOPE", "DOES_NOT_SUPPORT", "INSUFFICIENT_EVIDENCE", "CANNOT_DETERMINE"
        }
        checks["no_strategy_handoff_claim"] = "strategy qualification" in result["claim"]
    payload = {
        "validated_at_utc": now_utc(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "json_files_checked": len(list(HERE.glob("*.json"))),
        "csv_files_checked": len(list(HERE.glob("*.csv"))),
    }
    write_json(HERE / "validation.json", payload)
    print(json.dumps({"status": payload["status"], "check_count": len(checks)}))
    if payload["status"] != "PASS":
        raise RuntimeError(f"validation failed: {checks}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Relative signed jump and next-day return predictability")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    for name, function in (("fetch", command_fetch), ("inspect", command_inspect), ("analyze", command_analyze), ("gate", command_gate)):
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=function)
    sub.add_parser("conclude").set_defaults(func=command_conclude)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
