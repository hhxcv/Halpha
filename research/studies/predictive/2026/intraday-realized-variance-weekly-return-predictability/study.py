from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
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
PARENT_DIR = ROOT / "research/studies/predictive/2026/relative-signed-jump-next-day-predictability"
PARENT_STUDY = PARENT_DIR / "study.py"
PARENT_SOURCE = PARENT_DIR / "source_manifest_development.json"
PARENT_SOURCE_SHA256 = "8f0404a9d1b6e1d03db1b977a534706a5496a24324afc11cf1d9e53183ae8d8c"
PARENT_SOURCE_CONTENT_DIGEST = "ca419060bd58d89a86c8b652446008e005952dbf4b178daebc34dd56105aa4ff"
DATA_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "intraday-realized-variance-weekly-return-predictability/2026-07-22-v1"
)
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
CONFIG = {
    "predictor_id": "RESEARCH_RV15M28_HIGH_NEXT_WEEK_V1",
    "rv_days": 28,
    "neighbor_days": [21, 35],
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "minimum_rankable": 20,
    "tail_fraction": 1.0 / 3.0,
    "beta_days": 84,
    "decision_weekday": "W-SAT",
    "entry_delay_days": 2,
    "target_days": 7,
    "stress_round_trip_underlying": 0.0052,
    "economic_notional_fraction": 0.25,
    "annual_full_plan_hurdle": 0.04,
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "hac_maxlags": 4,
    "minimum_action_weeks": 52,
    "minimum_negative_spread_fraction": 0.52,
    "minimum_selected_symbols": 10,
    "minimum_positive_symbol_fraction": 0.50,
    "maximum_positive_contribution_share": 0.35,
    "download_workers": 8,
}
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PARENT = load_module(PARENT_STUDY, "halpha_rsj_parent")


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
    if digest_file(PARENT_SOURCE) != PARENT_SOURCE_SHA256:
        raise RuntimeError("parent development source manifest byte identity changed")
    parent = read_json(PARENT_SOURCE)
    if parent["content_digest"] != PARENT_SOURCE_CONTENT_DIGEST:
        raise RuntimeError("parent development source manifest content identity changed")
    frozen = {
        name: digest_file(HERE / name)
        for name in ["README.md", "sources.md", "preregistration.md", "study.py"]
    }
    payload = {
        "created_at_utc": now_utc(),
        "baseline_commit": BASELINE_COMMIT,
        "formal_strategy_background": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP",
        "research_kind": "PREDICTIVE",
        "question": (
            "Does 28 complete UTC days of 15-minute realized total variance negatively predict "
            "next-week returns among 25 mature Binance USD-M perpetuals, incrementally versus "
            "daily volatility, with enough high-RV single-short gross room for a separate strategy study?"
        ),
        "hypothesis_direction": "negative high-minus-low return, negative rank IC and negative controlled RV slope",
        "stages": STAGES,
        "config": CONFIG,
        "symbols": SYMBOLS,
        "frozen_file_sha256": frozen,
        "development_source": {
            "path": str(PARENT_SOURCE.relative_to(ROOT)).replace("\\", "/"),
            "sha256": PARENT_SOURCE_SHA256,
            "content_digest": PARENT_SOURCE_CONTENT_DIGEST,
            "archive_count": parent["archive_count"],
            "archive_bytes": parent["archive_bytes"],
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "stage_open_rule": "development -> evaluation only on PASS -> confirmation only on PASS",
        "strategy_conversion_rule": "only after all three predictive stages PASS; funding strategy study remains separate",
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"digest": read_json(HERE / "checkpoint.json")["content_digest"]}))


def assert_checkpoint() -> None:
    checkpoint = read_json(HERE / "checkpoint.json")
    checks = {
        name: checkpoint["frozen_file_sha256"][name] == digest_file(HERE / name)
        for name in checkpoint["frozen_file_sha256"]
    }
    if not all(checks.values()):
        raise RuntimeError(f"frozen method identity changed: {checks}")
    if digest_file(PARENT_SOURCE) != PARENT_SOURCE_SHA256:
        raise RuntimeError("parent source identity changed")
    if read_json(PARENT_SOURCE)["content_digest"] != PARENT_SOURCE_CONTENT_DIGEST:
        raise RuntimeError("parent source content identity changed")


def stage_authorized(stage: str) -> None:
    if stage == "evaluation":
        gate = HERE / "development_gate.json"
        if not gate.exists() or read_json(gate)["status"] != "PASS":
            raise RuntimeError("evaluation sealed until development PASS")
    if stage == "confirmation":
        gate = HERE / "evaluation_gate.json"
        if not gate.exists() or read_json(gate)["status"] != "PASS":
            raise RuntimeError("confirmation sealed until evaluation PASS")


def stage_bounds_for_archives(stage: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = map(pd.Timestamp, STAGES[stage])
    return start - pd.Timedelta(days=36, minutes=15), end + pd.Timedelta(days=1)


def archive_specs(stage: str) -> list[dict[str, str]]:
    start, end = stage_bounds_for_archives(stage)
    months = pd.date_range(start.normalize().replace(day=1), end.normalize().replace(day=1), freq="MS")
    specs: list[dict[str, str]] = []
    for symbol in SYMBOLS:
        for month in months:
            if month == pd.Timestamp("2026-07-01T00:00:00Z"):
                day_start = max(start.normalize(), month)
                day_end = min(end.normalize(), pd.Timestamp("2026-07-22T00:00:00Z"))
                for day in pd.date_range(day_start, day_end, freq="1D", inclusive="left"):
                    token = day.strftime("%Y-%m-%d")
                    filename = f"{symbol}-15m-{token}.zip"
                    specs.append({
                        "symbol": symbol,
                        "kind": "daily",
                        "period": token,
                        "filename": filename,
                        "url": f"{ARCHIVE_BASE}/daily/klines/{symbol}/15m/{filename}",
                    })
            else:
                token = month.strftime("%Y-%m")
                filename = f"{symbol}-15m-{token}.zip"
                specs.append({
                    "symbol": symbol,
                    "kind": "monthly",
                    "period": token,
                    "filename": filename,
                    "url": f"{ARCHIVE_BASE}/monthly/klines/{symbol}/15m/{filename}",
                })
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
    raise RuntimeError(f"download failed: {url}: {last}")


def download_archive(stage: str, spec: dict[str, str]) -> dict[str, Any]:
    directory = DATA_ROOT / stage / spec["symbol"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / spec["filename"]
    checksum_url = spec["url"] + ".CHECKSUM"
    checksum_raw = fetch_url(checksum_url)
    upstream_sha = checksum_raw.decode("utf-8").strip().split()[0].lower()
    if len(upstream_sha) != 64:
        raise RuntimeError(f"invalid checksum: {checksum_url}")
    if path.exists() and digest_file(path) == upstream_sha:
        downloaded_now = False
    else:
        raw = fetch_url(spec["url"])
        if digest_bytes(raw) != upstream_sha:
            raise RuntimeError(f"checksum mismatch: {spec['url']}")
        partial = path.with_suffix(path.suffix + ".partial")
        partial.write_bytes(raw)
        partial.replace(path)
        downloaded_now = True
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
        "downloaded_now": downloaded_now,
    }


def command_fetch(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    if args.stage == "development":
        print(json.dumps({"stage": args.stage, "decision": "REUSE_PARENT_SOURCE; no download"}))
        return
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
    }
    write_json(HERE / f"source_manifest_{args.stage}.json", payload)
    print(json.dumps({"stage": args.stage, "archives": len(results), "bytes": payload["archive_bytes"]}))


def verified_archive(item: dict[str, Any]) -> bytes:
    path = Path(item["path"])
    raw = path.read_bytes()
    if len(raw) != int(item["bytes"]) or digest_bytes(raw) != item["sha256"]:
        raise RuntimeError(f"archive identity mismatch: {path}")
    if item["sha256"] != item["upstream_sha256"]:
        raise RuntimeError(f"archive upstream identity mismatch: {path}")
    return raw


def read_archive_frame(item: dict[str, Any]) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(verified_archive(item))) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise RuntimeError(f"unexpected archive members: {item['path']}")
        with archive.open(names[0]) as member:
            frame = pd.read_csv(member, header=None, names=KLINE_COLUMNS, dtype=str)
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="coerce")
    frame = frame[frame["open_time"].notna()].copy()
    frame["open_time"] = pd.to_datetime(frame["open_time"].astype("int64"), unit="ms", utc=True)
    for column in ["open", "high", "low", "close", "volume", "quote_volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame


def load_intraday(stage: str) -> dict[str, pd.DataFrame]:
    if stage == "development":
        return PARENT.load_intraday("development")
    manifest = read_json(HERE / f"source_manifest_{stage}.json")
    if manifest["stage"] != stage or not manifest["upstream_checksums_verified"]:
        raise RuntimeError("invalid source manifest")
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


def source_identity(stage: str) -> dict[str, Any]:
    if stage == "development":
        source = read_json(PARENT_SOURCE)
        return {
            "kind": "verified_reuse",
            "path": str(PARENT_SOURCE.relative_to(ROOT)).replace("\\", "/"),
            "sha256": PARENT_SOURCE_SHA256,
            "content_digest": PARENT_SOURCE_CONTENT_DIGEST,
            "archive_count": source["archive_count"],
            "archive_bytes": source["archive_bytes"],
        }
    source_path = HERE / f"source_manifest_{stage}.json"
    source = read_json(source_path)
    return {
        "kind": "study_cache",
        "path": str(source_path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": digest_file(source_path),
        "content_digest": source["content_digest"],
        "archive_count": source["archive_count"],
        "archive_bytes": source["archive_bytes"],
    }


def decision_times(stage: str) -> list[pd.Timestamp]:
    start, end = map(pd.Timestamp, STAGES[stage])
    values = pd.date_range(start, end, freq=str(CONFIG["decision_weekday"]), inclusive="left")
    return [
        value for value in values
        if value + pd.Timedelta(days=int(CONFIG["entry_delay_days"] + CONFIG["target_days"])) <= end
    ]


def complete_rv_window(frame: pd.DataFrame, decision: pd.Timestamp, days: int) -> bool:
    first = decision - pd.Timedelta(days=days, minutes=15)
    last = decision - pd.Timedelta(minutes=15)
    expected = pd.date_range(first, last, freq="15min")
    return len(expected) == days * 96 + 1 and expected.isin(frame.index).all()


def command_prepare(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    if args.stage != "development" and not (HERE / f"source_manifest_{args.stage}.json").exists():
        raise RuntimeError(f"fetch {args.stage} before prepare")
    if args.stage == "development":
        reuse = {
            "created_at_utc": now_utc(),
            "purpose": "reuse official 15m archives without copying or redownloading",
            "upstream": source_identity("development"),
            "verification": "every archive is re-read with stored bytes/SHA-256/upstream checksum by parent loader",
            "product_data_used": False,
        }
        write_json(HERE / "source_reuse_manifest.json", reuse)
    bars = load_intraday(args.stage)
    decisions = decision_times(args.stage)
    source_checks: dict[str, Any] = {}
    status = True
    for symbol, frame in bars.items():
        duplicate_count = int(frame.index.duplicated().sum())
        invalid_ohlc = int(((frame[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
        invalid_range = int(((frame["high"] < frame[["open", "close"]].max(axis=1)) | (frame["low"] > frame[["open", "close"]].min(axis=1))).sum())
        complete = 0
        for decision in decisions:
            entry = decision + pd.Timedelta(days=int(CONFIG["entry_delay_days"]))
            exit_time = entry + pd.Timedelta(days=int(CONFIG["target_days"]))
            if complete_rv_window(frame, decision, max(CONFIG["neighbor_days"])) and entry in frame.index and exit_time in frame.index:
                complete += 1
        source_checks[symbol] = {
            "rows": int(len(frame)),
            "first": frame.index.min().isoformat(),
            "last": frame.index.max().isoformat(),
            "duplicates": duplicate_count,
            "invalid_ohlc": invalid_ohlc,
            "invalid_range": invalid_range,
            "complete_rv35_and_target_weeks": complete,
            "expected_weeks": len(decisions),
        }
        status = status and duplicate_count == 0 and invalid_ohlc == 0 and invalid_range == 0
    payload = {
        "checked_at_utc": now_utc(),
        "stage": args.stage,
        "status": "PASS" if status else "FAIL",
        "expected_decision_weeks": len(decisions),
        "symbols": source_checks,
        "source": source_identity(args.stage),
        "minimum_complete_symbol_weeks": min(item["complete_rv35_and_target_weeks"] for item in source_checks.values()),
        "maximum_complete_symbol_weeks": max(item["complete_rv35_and_target_weeks"] for item in source_checks.values()),
    }
    write_json(HERE / f"data_quality_{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage,
        "status": payload["status"],
        "weeks": len(decisions),
        "complete_range": [payload["minimum_complete_symbol_weeks"], payload["maximum_complete_symbol_weeks"]],
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


def realized_variance(frame: pd.DataFrame, decision: pd.Timestamp, days: int) -> float | None:
    first = decision - pd.Timedelta(days=days, minutes=15)
    last = decision - pd.Timedelta(minutes=15)
    expected = pd.date_range(first, last, freq="15min")
    if len(expected) != days * 96 + 1 or not expected.isin(frame.index).all():
        return None
    closes = frame.loc[expected, "close"].to_numpy(float)
    returns = np.diff(np.log(closes))
    value = float(np.sum(returns * returns))
    return value if math.isfinite(value) and value > 0 else None


def build_panel(stage: str) -> pd.DataFrame:
    intraday = load_intraday(stage)
    daily, _exchange = PARENT.load_daily()
    daily_returns = daily_return_frame(daily)
    market = daily_returns.mean(axis=1, skipna=True)
    rows: list[dict[str, Any]] = []
    for decision in decision_times(stage):
        entry = decision + pd.Timedelta(days=int(CONFIG["entry_delay_days"]))
        exit_time = entry + pd.Timedelta(days=int(CONFIG["target_days"]))
        for symbol in SYMBOLS:
            frame = intraday[symbol]
            rv_values = {days: realized_variance(frame, decision, days) for days in [21, 28, 35]}
            if any(value is None for value in rv_values.values()) or entry not in frame.index or exit_time not in frame.index:
                continue
            history28 = daily_returns[symbol].loc[decision - pd.Timedelta(days=28): decision - pd.Timedelta(days=1)].dropna()
            history84 = daily_returns[symbol].loc[decision - pd.Timedelta(days=84): decision - pd.Timedelta(days=1)].dropna()
            market84 = market.reindex(history84.index).dropna()
            history84 = history84.reindex(market84.index).dropna()
            volume30 = daily[symbol]["quote_volume"].loc[decision - pd.Timedelta(days=30): decision - pd.Timedelta(days=1)].dropna()
            if len(history28) != 28 or len(history84) < 80 or len(volume30) < 28:
                continue
            median_volume = float(volume30.median())
            if median_volume < float(CONFIG["minimum_median_quote_volume_30d"]):
                continue
            entry_open = float(frame.at[entry, "open"])
            exit_open = float(frame.at[exit_time, "open"])
            next_return = exit_open / entry_open - 1.0
            rows.append({
                "decision": decision,
                "entry": entry,
                "exit": exit_time,
                "symbol": symbol,
                "rv21": rv_values[21],
                "rv28": rv_values[28],
                "rv35": rv_values[35],
                "dvol28": float(history28.std(ddof=1)),
                "mom28": float(np.prod(1.0 + history28.to_numpy(float)) - 1.0),
                "max28": float(history28.max()),
                "beta84": fit_beta(history84, market84),
                "log_volume30": float(np.log(median_volume)),
                "next_week_return": float(next_return),
            })
    panel = pd.DataFrame(rows)
    if panel.empty:
        raise RuntimeError("empty weekly panel")
    panel = panel.sort_values(["decision", "symbol"]).reset_index(drop=True)
    counts = panel.groupby("decision")["symbol"].count()
    eligible = counts[counts >= int(CONFIG["minimum_rankable"])].index
    return panel[panel["decision"].isin(eligible)].reset_index(drop=True)


def circular_block_ci(values: np.ndarray, seed_offset: int = 0) -> list[float]:
    clean = np.asarray(values, dtype=float)
    if len(clean) == 0:
        return [float("nan"), float("nan")]
    block = int(CONFIG["bootstrap"]["block_weeks"])
    repetitions = int(CONFIG["bootstrap"]["repetitions"])
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"]) + seed_offset)
    means = np.empty(repetitions)
    blocks_needed = math.ceil(len(clean) / block)
    offsets = np.arange(block)
    for index in range(repetitions):
        starts = rng.integers(0, len(clean), size=blocks_needed)
        sample_index = ((starts[:, None] + offsets) % len(clean)).ravel()[: len(clean)]
        means[index] = float(clean[sample_index].mean())
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def series_summary(values: pd.Series | np.ndarray, seed_offset: int = 0) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    return {
        "observations": int(len(array)),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "bootstrap_95pct": circular_block_ci(array, seed_offset),
        "positive_fraction": float(np.mean(array > 0)),
        "negative_fraction": float(np.mean(array < 0)),
        "minimum": float(array.min()),
        "maximum": float(array.max()),
    }


def hac_mean(values: np.ndarray, expected_negative: bool) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    result = sm.OLS(array, np.ones((len(array), 1))).fit(
        cov_type="HAC", cov_kwds={"maxlags": int(CONFIG["hac_maxlags"])}
    )
    coefficient = float(result.params[0])
    two_sided = float(result.pvalues[0])
    if expected_negative:
        one_sided = two_sided / 2.0 if coefficient < 0 else 1.0 - two_sided / 2.0
    else:
        one_sided = two_sided / 2.0 if coefficient > 0 else 1.0 - two_sided / 2.0
    return {
        "mean": coefficient,
        "hac_standard_error": float(result.bse[0]),
        "two_sided_p": two_sided,
        "one_sided_p": float(one_sided),
    }


def proxy_return(underlying_return: float) -> float:
    return (
        float(CONFIG["economic_notional_fraction"])
        * (-underlying_return - float(CONFIG["stress_round_trip_underlying"]))
        - float(CONFIG["annual_full_plan_hurdle"]) / 52.0
    )


def weekly_outputs(panel: pd.DataFrame, signal: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for decision, group in panel.groupby("decision", sort=True):
        group = group.sort_values([signal, "symbol"]).reset_index(drop=True)
        tail = int(math.ceil(len(group) * float(CONFIG["tail_fraction"])))
        low = group.head(tail)
        high = group.tail(tail)
        ic = spearmanr(group[signal], group["next_week_return"]).statistic
        chosen = group.sort_values([signal, "symbol"], ascending=[False, True]).iloc[0]
        dvol = group.sort_values(["dvol28", "symbol"], ascending=[False, True]).iloc[0]
        selected.append({
            "decision": decision,
            "entry": chosen["entry"],
            "exit": chosen["exit"],
            "symbol": chosen["symbol"],
            "signal": signal,
            "signal_value": float(chosen[signal]),
            "underlying_return": float(chosen["next_week_return"]),
            "short_proxy": proxy_return(float(chosen["next_week_return"])),
            "dvol_symbol": dvol["symbol"],
            "dvol_underlying_return": float(dvol["next_week_return"]),
            "dvol_short_proxy": proxy_return(float(dvol["next_week_return"])),
        })
        rows.append({
            "decision": decision,
            "entry": chosen["entry"],
            "rankable": int(len(group)),
            "tail_size": tail,
            "low_return": float(low["next_week_return"].mean()),
            "high_return": float(high["next_week_return"].mean()),
            "high_minus_low": float(high["next_week_return"].mean() - low["next_week_return"].mean()),
            "rank_ic": float(ic),
            "top_short_proxy": proxy_return(float(chosen["next_week_return"])),
            "dvol_top_short_proxy": proxy_return(float(dvol["next_week_return"])),
            "increment_vs_dvol": proxy_return(float(chosen["next_week_return"])) - proxy_return(float(dvol["next_week_return"])),
        })
    return pd.DataFrame(rows), pd.DataFrame(selected)


def standardized(group: pd.DataFrame, column: str) -> np.ndarray:
    values = group[column].to_numpy(float)
    scale = float(values.std(ddof=0))
    if scale <= 0:
        raise RuntimeError(f"zero cross-sectional scale: {column}")
    return (values - float(values.mean())) / scale


def fama_macbeth(panel: pd.DataFrame) -> dict[str, Any]:
    columns = ["rv28", "dvol28", "mom28", "max28", "beta84", "log_volume30"]
    coefficients: list[dict[str, float]] = []
    for decision, group in panel.groupby("decision", sort=True):
        design = np.column_stack([np.ones(len(group)), *[standardized(group, column) for column in columns]])
        fit = np.linalg.lstsq(design, group["next_week_return"].to_numpy(float), rcond=None)[0]
        coefficients.append({"decision": decision, **{column: float(fit[index + 1]) for index, column in enumerate(columns)}})
    frame = pd.DataFrame(coefficients)
    summaries = {column: hac_mean(frame[column].to_numpy(float), expected_negative=(column == "rv28")) for column in columns}
    return {"weekly_coefficients": frame, "summaries": summaries}


def breadth(selected: pd.DataFrame) -> dict[str, Any]:
    by_symbol = []
    for symbol, group in selected.groupby("symbol"):
        by_symbol.append({
            "symbol": symbol,
            "selections": int(len(group)),
            "mean_short_proxy": float(group["short_proxy"].mean()),
            "total_short_proxy": float(group["short_proxy"].sum()),
        })
    frame = pd.DataFrame(by_symbol)
    repeated = frame[frame["selections"] >= 2]
    positive = frame[frame["total_short_proxy"] > 0]["total_short_proxy"]
    maximum_share = float(positive.max() / positive.sum()) if len(positive) and positive.sum() > 0 else 1.0
    return {
        "selected_symbols": int(len(frame)),
        "repeated_symbols": int(len(repeated)),
        "positive_mean_symbol_fraction": float((repeated["mean_short_proxy"] > 0).mean()) if len(repeated) else 0.0,
        "maximum_positive_contribution_share": maximum_share,
        "by_symbol": by_symbol,
    }


def summarize(stage: str, panel: pd.DataFrame) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    weekly, selected = weekly_outputs(panel, "rv28")
    neighbor_summaries: dict[str, Any] = {}
    for days in CONFIG["neighbor_days"]:
        neighbor_weekly, _neighbor_selected = weekly_outputs(panel, f"rv{days}")
        neighbor_summaries[f"rv{days}"] = {
            "high_minus_low": series_summary(neighbor_weekly["high_minus_low"], seed_offset=days),
            "top_short_proxy": series_summary(neighbor_weekly["top_short_proxy"], seed_offset=100 + days),
        }
    fmb = fama_macbeth(panel)
    rank_ic = hac_mean(weekly["rank_ic"].to_numpy(float), expected_negative=True)
    midpoint = len(weekly) // 2
    halves = {
        "first": series_summary(weekly.iloc[:midpoint]["top_short_proxy"], seed_offset=201),
        "second": series_summary(weekly.iloc[midpoint:]["top_short_proxy"], seed_offset=202),
    }
    calendar_years = {
        str(year): series_summary(group["top_short_proxy"], seed_offset=300 + int(year))
        for year, group in weekly.groupby(pd.to_datetime(weekly["entry"], utc=True).dt.year)
    }
    breadth_result = breadth(selected)
    main = {
        "high_minus_low": series_summary(weekly["high_minus_low"], seed_offset=1),
        "rank_ic": rank_ic,
        "controlled_rv28": fmb["summaries"]["rv28"],
        "top_short_proxy": series_summary(weekly["top_short_proxy"], seed_offset=2),
        "dvol_top_short_proxy": series_summary(weekly["dvol_top_short_proxy"], seed_offset=3),
        "increment_vs_dvol": series_summary(weekly["increment_vs_dvol"], seed_offset=4),
    }
    checks = {
        "data_quality_pass": read_json(HERE / f"data_quality_{stage}.json")["status"] == "PASS",
        "minimum_action_weeks": len(weekly) >= int(CONFIG["minimum_action_weeks"]),
        "minimum_rankable_each_week": int(weekly["rankable"].min()) >= int(CONFIG["minimum_rankable"]),
        "spread_mean_negative": main["high_minus_low"]["mean"] < 0.0,
        "spread_bootstrap_upper_negative": main["high_minus_low"]["bootstrap_95pct"][1] < 0.0,
        "spread_negative_fraction": main["high_minus_low"]["negative_fraction"] >= float(CONFIG["minimum_negative_spread_fraction"]),
        "rank_ic_negative": rank_ic["mean"] < 0.0,
        "rank_ic_negative_significant": rank_ic["one_sided_p"] < 0.05,
        "controlled_rv_negative": fmb["summaries"]["rv28"]["mean"] < 0.0,
        "controlled_rv_negative_significant": fmb["summaries"]["rv28"]["one_sided_p"] < 0.05,
        "proxy_mean_positive": main["top_short_proxy"]["mean"] > 0.0,
        "proxy_bootstrap_lower_positive": main["top_short_proxy"]["bootstrap_95pct"][0] > 0.0,
        "increment_vs_dvol_positive": main["increment_vs_dvol"]["mean"] > 0.0,
        "increment_vs_dvol_bootstrap_lower_positive": main["increment_vs_dvol"]["bootstrap_95pct"][0] > 0.0,
        "both_halves_positive": all(item["mean"] > 0.0 for item in halves.values()),
        "all_calendar_years_positive": all(item["mean"] > 0.0 for item in calendar_years.values()),
        "all_neighbors_directional": all(
            item["high_minus_low"]["mean"] < 0.0 and item["top_short_proxy"]["mean"] > 0.0
            for item in neighbor_summaries.values()
        ),
        "minimum_selected_symbols": breadth_result["selected_symbols"] >= int(CONFIG["minimum_selected_symbols"]),
        "positive_symbol_breadth": breadth_result["positive_mean_symbol_fraction"] >= float(CONFIG["minimum_positive_symbol_fraction"]),
        "positive_contribution_not_concentrated": breadth_result["maximum_positive_contribution_share"] <= float(CONFIG["maximum_positive_contribution_share"]),
    }
    payload = {
        "stage": stage,
        "period": {"start": STAGES[stage][0], "end_exclusive": STAGES[stage][1]},
        "checkpoint_digest": read_json(HERE / "checkpoint.json")["content_digest"],
        "source": source_identity(stage),
        "data_quality_digest": read_json(HERE / f"data_quality_{stage}.json")["content_digest"],
        "question_result": "SUPPORTS_WITHIN_SCOPE" if all(checks.values()) else "DOES_NOT_SUPPORT",
        "release_next_stage": all(checks.values()),
        "panel_rows": int(len(panel)),
        "action_weeks": int(len(weekly)),
        "rankable_range": [int(weekly["rankable"].min()), int(weekly["rankable"].max())],
        "main": main,
        "halves": halves,
        "calendar_years": calendar_years,
        "neighbors": neighbor_summaries,
        "fama_macbeth": {"summaries": fmb["summaries"]},
        "breadth": breadth_result,
        "hard_gates": checks,
        "failed_hard_gates": [name for name, passed in checks.items() if not passed],
        "economic_proxy_limit": "0.25x one-leg high-RV short after 52bp underlying round-trip and 4% full-plan hurdle; funding and execution path absent",
        "strategy_conversion": "PROHIBITED_UNLESS_ALL_THREE_PREDICTIVE_STAGES_PASS",
    }
    frames = {
        f"{stage}_panel.csv": panel,
        f"{stage}_weekly.csv": weekly,
        f"{stage}_selected.csv": selected,
        f"{stage}_fmb_weekly.csv": fmb["weekly_coefficients"],
    }
    return payload, frames


def command_analyze(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    quality_path = HERE / f"data_quality_{args.stage}.json"
    if not quality_path.exists() or read_json(quality_path)["status"] != "PASS":
        raise RuntimeError("prepare and pass data quality before analyze")
    panel = build_panel(args.stage)
    payload, frames = summarize(args.stage, panel)
    payload["generated_at_utc"] = now_utc()
    for name, frame in frames.items():
        frame.to_csv(HERE / name, index=False, lineterminator="\n")
    payload["csv_sha256"] = {name: digest_file(HERE / name) for name in frames}
    write_json(HERE / f"{args.stage}.json", payload)
    output = read_json(HERE / f"{args.stage}.json")
    print(json.dumps({
        "stage": args.stage,
        "result": output["question_result"],
        "weeks": output["action_weeks"],
        "spread": output["main"]["high_minus_low"]["mean"],
        "proxy": output["main"]["top_short_proxy"]["mean"],
        "failed": output["failed_hard_gates"],
    }))


def command_gate(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    result = read_json(HERE / f"{args.stage}.json")
    status = "PASS" if result["release_next_stage"] else "FAIL"
    payload = {
        "created_at_utc": now_utc(),
        "stage": args.stage,
        "status": status,
        "result_digest": result["content_digest"],
        "checks": result["hard_gates"],
        "failed_checks": result["failed_hard_gates"],
        "next_stage": (
            "evaluation" if args.stage == "development" and status == "PASS"
            else "confirmation" if args.stage == "evaluation" and status == "PASS"
            else "strategy_candidate_question_allowed" if args.stage == "confirmation" and status == "PASS"
            else "SEALED"
        ),
    }
    write_json(HERE / f"{args.stage}_gate.json", payload)
    print(json.dumps({"stage": args.stage, "status": status, "failed": payload["failed_checks"]}))


def final_conclusion() -> tuple[str, str]:
    development_gate = HERE / "development_gate.json"
    if not development_gate.exists():
        return "CANNOT_DETERMINE", "development gate missing"
    if read_json(development_gate)["status"] == "FAIL":
        quality = read_json(HERE / "data_quality_development.json")
        if quality["status"] != "PASS":
            return "CANNOT_DETERMINE", "development data quality failed"
        return "DOES_NOT_SUPPORT", "development predictive gate failed; later stages and strategy conversion sealed"
    evaluation_gate = HERE / "evaluation_gate.json"
    if not evaluation_gate.exists():
        return "INSUFFICIENT_EVIDENCE", "development passed but evaluation not completed"
    if read_json(evaluation_gate)["status"] == "FAIL":
        return "DOES_NOT_SUPPORT", "evaluation failed; confirmation and strategy conversion sealed"
    confirmation_gate = HERE / "confirmation_gate.json"
    if not confirmation_gate.exists():
        return "INSUFFICIENT_EVIDENCE", "development and evaluation passed but confirmation not completed"
    if read_json(confirmation_gate)["status"] == "FAIL":
        return "DOES_NOT_SUPPORT", "confirmation failed; strategy conversion prohibited"
    return "SUPPORTS_WITHIN_SCOPE", "all three predictive stages passed; a separate funding-aware strategy candidate study is allowed"


def command_conclude(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    conclusion, reason = final_conclusion()
    development = read_json(HERE / "development.json") if (HERE / "development.json").exists() else None
    payload = {
        "created_at_utc": now_utc(),
        "question": read_json(HERE / "checkpoint.json")["question"],
        "conclusion": conclusion,
        "reason": reason,
        "development_gate": read_json(HERE / "development_gate.json")["status"] if (HERE / "development_gate.json").exists() else None,
        "evaluation_gate": read_json(HERE / "evaluation_gate.json")["status"] if (HERE / "evaluation_gate.json").exists() else None,
        "confirmation_gate": read_json(HERE / "confirmation_gate.json")["status"] if (HERE / "confirmation_gate.json").exists() else None,
        "development_digest": development["content_digest"] if development else None,
        "strategy_conversion": "ALLOWED_AS_SEPARATE_QUESTION" if conclusion == "SUPPORTS_WITHIN_SCOPE" else "PROHIBITED",
        "handoff_generated": False,
        "product_effects": "NONE",
    }
    write_json(HERE / "results.json", payload)
    if development:
        main = development["main"]
        text = f"""# 结果：15 分钟 realized variance 与下一周收益

## 结论

`{conclusion}`

{reason}。本题不生成交易核心 handoff，不修改正式策略、产品代码、L4、资金或真实账户。

## development 证据

- 有效周 / panel 行：`{development['action_weeks']} / {development['panel_rows']}`。
- RV28 high-minus-low：`{main['high_minus_low']['mean']:.6%}/周`，四周 block-bootstrap 95% 区间 `[{main['high_minus_low']['bootstrap_95pct'][0]:.6%}, {main['high_minus_low']['bootstrap_95pct'][1]:.6%}]`。
- rank IC：`{main['rank_ic']['mean']:.6f}`，负向单侧 HAC p=`{main['rank_ic']['one_sided_p']:.6f}`。
- 控制日线波动、MOM、MAX、beta、volume 后 RV28 系数：`{main['controlled_rv28']['mean']:.6%}`，负向单侧 HAC p=`{main['controlled_rv28']['one_sided_p']:.6f}`。
- 高 RV 单目标 SHORT 压力成本与完整资本门后粗代理：`{main['top_short_proxy']['mean']:.6%}/周`，95% 区间 `[{main['top_short_proxy']['bootstrap_95pct'][0]:.6%}, {main['top_short_proxy']['bootstrap_95pct'][1]:.6%}]`。
- 相对日线 DVOL28 高波 SHORT 增量：`{main['increment_vs_dvol']['mean']:.6%}/周`，95% 区间 `[{main['increment_vs_dvol']['bootstrap_95pct'][0]:.6%}, {main['increment_vs_dvol']['bootstrap_95pct'][1]:.6%}]`。
- 失败硬门：`{', '.join(development['failed_hard_gates']) if development['failed_hard_gates'] else 'none'}`。

## 解释边界

论文中的 100 个 spot、含小型/低流动币的宽组合结果不能直接代表当前 25 个成熟永续。预测题的粗代理没有 funding、盘口、排队、部分成交、保证金和人工激活路径；即使方向为正，也不能据此称为 Alpha 或长期盈利。后段是否开放严格由顺序 gate 决定。

## 复现

命令见 `README.md`。数据使用 Binance 官方公开 archive；development 复用 Git 外缓存并逐文件验证官方 checksum、本地 SHA-256 与字节数。`validation.json` 保存冻结文件、结果和 CSV 身份校验。
"""
    else:
        text = f"# 结果\n\n`{conclusion}`\n\n{reason}。\n"
    (HERE / "result.md").write_text(text, encoding="utf-8")
    print(json.dumps({"conclusion": conclusion, "reason": reason}))


def command_validate(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    checks: dict[str, bool] = {
        "parent_source_file_identity": digest_file(PARENT_SOURCE) == PARENT_SOURCE_SHA256,
        "parent_source_content_identity": read_json(PARENT_SOURCE)["content_digest"] == PARENT_SOURCE_CONTENT_DIGEST,
    }
    for stage in STAGES:
        result_path = HERE / f"{stage}.json"
        if not result_path.exists():
            continue
        result = read_json(result_path)
        checks[f"{stage}_checkpoint_identity"] = result["checkpoint_digest"] == read_json(HERE / "checkpoint.json")["content_digest"]
        checks[f"{stage}_data_quality_identity"] = result["data_quality_digest"] == read_json(HERE / f"data_quality_{stage}.json")["content_digest"]
        for name, expected in result["csv_sha256"].items():
            checks[f"{stage}_{name}_identity"] = digest_file(HERE / name) == expected
        gate = read_json(HERE / f"{stage}_gate.json")
        checks[f"{stage}_gate_result_identity"] = gate["result_digest"] == result["content_digest"]
        checks[f"{stage}_gate_consistency"] = (gate["status"] == "PASS") == bool(result["release_next_stage"])
    conclusion, _reason = final_conclusion()
    checks["final_conclusion_consistency"] = read_json(HERE / "results.json")["conclusion"] == conclusion
    payload = {
        "validated_at_utc": now_utc(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "results_sha256": digest_file(HERE / "results.json"),
        "result_md_sha256": digest_file(HERE / "result.md"),
    }
    write_json(HERE / "validation.json", payload)
    print(json.dumps({"status": payload["status"], "failed": [name for name, passed in checks.items() if not passed]}))
    if payload["status"] != "PASS":
        raise RuntimeError("validation failed")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    sub = value.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    for name, function in (
        ("fetch", command_fetch),
        ("prepare", command_prepare),
        ("analyze", command_analyze),
        ("gate", command_gate),
    ):
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=function)
    sub.add_parser("conclude").set_defaults(func=command_conclude)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return value


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
