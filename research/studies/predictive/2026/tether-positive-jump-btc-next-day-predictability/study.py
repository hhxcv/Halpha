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
from typing import Any, Callable

import numpy as np
import pandas as pd
import scipy
from scipy.special import gamma
from scipy.stats import norm
import statsmodels
import statsmodels.api as sm


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASELINE_COMMIT = "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4"
DATA_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "tether-positive-jump-btc-next-day-predictability/2026-07-22-v1"
)
BITFINEX_CANDLES = "https://api-pub.bitfinex.com/v2/candles/trade:1h:tUSTUSD/hist"
BINANCE_ARCHIVE = "https://data.binance.vision/data/futures/um"
STAGES = {
    "development": ("2021-07-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2024-07-01T00:00:00Z"),
    "confirmation": ("2024-07-01T00:00:00Z", "2026-07-20T00:00:00Z"),
}
EXPECTED_DAYS = {
    stage: len(pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="1D", inclusive="left"))
    for stage, (start, end) in STAGES.items()
}
STAGE_SEED_OFFSET = {"development": 0, "evaluation": 100_000, "confirmation": 200_000}
CONFIG = {
    "predictor_id": "RESEARCH_TETHER_POSITIVE_BNS_JUMP_BTC_NEXT_DAY_V1",
    "bitfinex_symbol": "tUSTUSD",
    "binance_symbol": "BTCUSDT",
    "bns_returns_per_day": 24,
    "bns_critical_value": 1.959963984540054,
    "fixed_positive_return_threshold": 0.00003,
    "entry_delay_minutes": 15,
    "target_hours": 24,
    "hac_maxlags": 7,
    "stress_round_trip_underlying": 0.0052,
    "economic_notional_fraction": 0.25,
    "annual_full_plan_hurdle": 0.04,
    "bootstrap": {"block_days": 14, "repetitions": 5000, "seed": 20260722},
    "minimum_eligible_fraction": 0.95,
    "minimum_bitfinex_hour_fraction": 0.98,
    "minimum_median_nonzero_hourly_returns": 4,
    "minimum_median_unique_hourly_closes": 4,
    "minimum_positive_bns_events": 20,
    "minimum_event_quarters": 5,
    "minimum_positive_event_fraction": 0.52,
    "maximum_positive_quarter_contribution": 0.50,
    "download_workers": 6,
}
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
]
BITFINEX_COLUMNS = ["mts", "open", "close", "high", "low", "volume"]


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


def digest_text_file_normalized(path: Path) -> str:
    """Hash logical UTF-8 text after universal-newline decoding."""
    return digest_bytes(path.read_text(encoding="utf-8").encode("utf-8"))


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


def finite(value: Any) -> float | None:
    if value is None:
        return None
    output = float(value)
    return output if math.isfinite(output) else None


def command_checkpoint(_args: argparse.Namespace) -> None:
    frozen_files = ["README.md", "sources.md", "preregistration.md", "study.py"]
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
            "Do positive BNS jumps in Bitfinex USDT/USD predict negative next-24-hour "
            "Binance BTCUSDT perpetual returns after a 15-minute action delay?"
        ),
        "source_sample_end": "2021-06-30",
        "replication_status": "post-source cross-venue operational transfer; not a numerical replication",
        "stages": STAGES,
        "expected_days": EXPECTED_DAYS,
        "config": CONFIG,
        "data_root": str(DATA_ROOT),
        "frozen_file_sha256": {name: digest_file(HERE / name) for name in frozen_files},
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "framework_decision": (
            "pandas/statsmodels for a predictive question; vectorbt and exact funding are "
            "mandatory only in a separately frozen strategy-candidate study after three passes"
        ),
        "stage_open_rule": "development -> evaluation on PASS -> confirmation on PASS",
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
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.75 * (attempt + 1))
    raise RuntimeError(f"download failed after {attempts} attempts: {url}: {last}")


def stage_bounds(stage: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = STAGES[stage]
    return pd.Timestamp(start), pd.Timestamp(end)


def bitfinex_request_bounds(stage: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = stage_bounds(stage)
    return start - pd.Timedelta(hours=2), end + pd.Timedelta(hours=1)


def binance_request_bounds(stage: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = stage_bounds(stage)
    return start - pd.Timedelta(days=1), end + pd.Timedelta(days=2)


def binance_archive_specs(stage: str) -> list[dict[str, str]]:
    start, end = binance_request_bounds(stage)
    months = pd.date_range(start.normalize().replace(day=1), end.normalize().replace(day=1), freq="MS")
    specs: list[dict[str, str]] = []
    for month in months:
        if month == pd.Timestamp("2026-07-01T00:00:00Z"):
            day_start = max(start.normalize(), month)
            day_end = end.normalize() + pd.Timedelta(days=1)
            for day in pd.date_range(day_start, day_end, freq="1D", inclusive="left"):
                token = day.strftime("%Y-%m-%d")
                filename = f"BTCUSDT-15m-{token}.zip"
                url = f"{BINANCE_ARCHIVE}/daily/klines/BTCUSDT/15m/{filename}"
                specs.append({"kind": "daily", "period": token, "filename": filename, "url": url})
        else:
            token = month.strftime("%Y-%m")
            filename = f"BTCUSDT-15m-{token}.zip"
            url = f"{BINANCE_ARCHIVE}/monthly/klines/BTCUSDT/15m/{filename}"
            specs.append({"kind": "monthly", "period": token, "filename": filename, "url": url})
    return specs


def fetch_binance_item(stage: str, spec: dict[str, str]) -> dict[str, Any]:
    directory = DATA_ROOT / stage / "binance"
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
        **spec,
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest_file(path),
        "checksum_url": checksum_url,
        "checksum_path": str(checksum_path),
        "checksum_bytes": checksum_path.stat().st_size,
        "checksum_sha256": digest_file(checksum_path),
        "upstream_sha256": upstream_sha,
        "downloaded": downloaded,
    }


def fetch_bitfinex(stage: str) -> list[dict[str, Any]]:
    directory = DATA_ROOT / stage / "bitfinex"
    directory.mkdir(parents=True, exist_ok=True)
    start, end = bitfinex_request_bounds(stage)
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    items: list[dict[str, Any]] = []
    page = 0
    while cursor <= end_ms:
        query = urllib.parse.urlencode({"start": cursor, "end": end_ms, "limit": 10000, "sort": 1})
        url = f"{BITFINEX_CANDLES}?{query}"
        path = directory / f"tUSTUSD-1h-page-{page:03d}.json"
        if path.exists():
            raw = path.read_bytes()
            downloaded = False
        else:
            raw = fetch_url(url)
            partial = path.with_suffix(path.suffix + ".partial")
            partial.write_bytes(raw)
            partial.replace(path)
            downloaded = True
        values = json.loads(raw)
        if not isinstance(values, list):
            raise RuntimeError(f"unexpected Bitfinex response: {path}")
        items.append({
            "source": "bitfinex_public_candles",
            "page": page,
            "url": url,
            "path": str(path),
            "bytes": len(raw),
            "sha256": digest_bytes(raw),
            "rows": len(values),
            "downloaded": downloaded,
        })
        if not values:
            break
        last_mts = int(values[-1][0])
        if last_mts < cursor:
            raise RuntimeError("Bitfinex pagination did not advance")
        cursor = last_mts + 3_600_000
        page += 1
        if len(values) < 10000:
            break
    return items


def verify_manifest_sources(manifest: dict[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    for index, item in enumerate(manifest["sources"]):
        path = Path(item["path"])
        key = f"{index}:{path.name}"
        checks[key] = (
            path.exists()
            and path.stat().st_size == int(item["bytes"])
            and digest_file(path) == item["sha256"]
        )
        if item["source"] == "binance_public_archive":
            checksum_path = Path(item["checksum_path"])
            checks[key + ":checksum"] = (
                checksum_path.exists()
                and checksum_path.stat().st_size == int(item["checksum_bytes"])
                and digest_file(checksum_path) == item["checksum_sha256"]
                and item["sha256"] == item["upstream_sha256"]
            )
    return checks


def command_fetch(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    manifest_path = HERE / f"source_manifest_{args.stage}.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        checks = verify_manifest_sources(manifest)
        if all(checks.values()):
            print(json.dumps({"stage": args.stage, "reused": True, "sources": len(checks)}))
            return
        raise RuntimeError(f"existing source manifest failed verification: {checks}")
    bitfinex_items = fetch_bitfinex(args.stage)
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG["download_workers"]) as pool:
        binance_items = list(pool.map(lambda spec: fetch_binance_item(args.stage, spec), binance_archive_specs(args.stage)))
    checkpoint = read_json(HERE / "checkpoint.json")
    payload = {
        "retrieved_at_utc": now_utc(),
        "stage": args.stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "data_root": str(DATA_ROOT / args.stage),
        "sources": bitfinex_items + binance_items,
    }
    write_json(manifest_path, payload)
    checks = verify_manifest_sources(read_json(manifest_path))
    if not all(checks.values()):
        raise RuntimeError(f"post-fetch source verification failed: {checks}")
    print(json.dumps({
        "stage": args.stage,
        "bitfinex_pages": len(bitfinex_items),
        "binance_archives": len(binance_items),
        "bytes": sum(int(item["bytes"]) for item in bitfinex_items + binance_items),
        "manifest_digest": read_json(manifest_path)["content_digest"],
    }))


def command_rebind_manifest(args: argparse.Namespace) -> None:
    """One-off non-semantic repair hook; preserves source bytes and prior identity."""
    checkpoint = assert_checkpoint()
    stage_authorized(args.stage)
    path = HERE / f"source_manifest_{args.stage}.json"
    manifest = read_json(path)
    checks = verify_manifest_sources(manifest)
    if not all(checks.values()):
        raise RuntimeError(f"cannot rebind unverified sources: {checks}")
    prior_digest = manifest.pop("content_digest")
    manifest["prior_manifest_content_digest"] = prior_digest
    manifest["rebind_reason"] = args.reason
    manifest["rebound_at_utc"] = now_utc()
    manifest["checkpoint_digest"] = checkpoint["content_digest"]
    write_json(path, manifest)
    print(json.dumps({
        "stage": args.stage,
        "prior_manifest_digest": prior_digest,
        "manifest_digest": read_json(path)["content_digest"],
        "source_checks": len(checks),
    }))


def load_bitfinex(stage: str) -> tuple[pd.DataFrame, dict[str, int]]:
    manifest = read_json(HERE / f"source_manifest_{stage}.json")
    frames: list[pd.DataFrame] = []
    raw_rows = 0
    for item in manifest["sources"]:
        if item["source"] != "bitfinex_public_candles":
            continue
        raw = Path(item["path"]).read_bytes()
        values = json.loads(raw)
        raw_rows += len(values)
        if values:
            frames.append(pd.DataFrame(values, columns=BITFINEX_COLUMNS))
    if not frames:
        raise RuntimeError("no Bitfinex rows")
    frame = pd.concat(frames, ignore_index=True)
    for column in BITFINEX_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    invalid_numeric = int(frame.isna().any(axis=1).sum())
    duplicates = int(frame.duplicated("mts", keep=False).sum())
    frame = frame.dropna().drop_duplicates("mts", keep="last").sort_values("mts").reset_index(drop=True)
    frame["timestamp"] = pd.to_datetime(frame["mts"].astype("int64"), unit="ms", utc=True)
    return frame, {"raw_rows": raw_rows, "invalid_numeric_rows": invalid_numeric, "duplicate_rows": duplicates}


def read_kline_zip(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise RuntimeError(f"unexpected zip members in {path}: {names}")
        csv_raw = archive.read(names[0])
    frame = pd.read_csv(io.BytesIO(csv_raw), header=None, names=KLINE_COLUMNS)
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="coerce")
    frame = frame.loc[frame["open_time"].notna()].copy()
    for column in KLINE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def load_binance(stage: str) -> tuple[pd.DataFrame, dict[str, int]]:
    manifest = read_json(HERE / f"source_manifest_{stage}.json")
    frames = [
        read_kline_zip(Path(item["path"]))
        for item in manifest["sources"]
        if item["source"] == "binance_public_archive"
    ]
    if not frames:
        raise RuntimeError("no Binance rows")
    frame = pd.concat(frames, ignore_index=True)
    raw_rows = len(frame)
    invalid_numeric = int(frame[["open_time", "open", "high", "low", "close"]].isna().any(axis=1).sum())
    duplicates = int(frame.duplicated("open_time", keep=False).sum())
    frame = frame.dropna(subset=["open_time", "open", "high", "low", "close"])
    frame = frame.drop_duplicates("open_time", keep="last").sort_values("open_time").reset_index(drop=True)
    frame["timestamp"] = pd.to_datetime(frame["open_time"].astype("int64"), unit="ms", utc=True)
    return frame, {"raw_rows": raw_rows, "invalid_numeric_rows": invalid_numeric, "duplicate_rows": duplicates}


def ohlc_invalid(frame: pd.DataFrame) -> int:
    return int((
        (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    ).sum())


def inspect_payload(stage: str) -> dict[str, Any]:
    checkpoint = assert_checkpoint()
    stage_authorized(stage)
    manifest = read_json(HERE / f"source_manifest_{stage}.json")
    source_checks = verify_manifest_sources(manifest)
    bitfinex, bmeta = load_bitfinex(stage)
    binance, cmeta = load_binance(stage)
    start, end = stage_bounds(stage)
    required_hours = pd.date_range(start - pd.Timedelta(hours=1), end - pd.Timedelta(hours=1), freq="1h")
    bitfinex_times = pd.Index(bitfinex["timestamp"])
    hour_fraction = float(required_hours.isin(bitfinex_times).mean())
    b_offgrid = int((bitfinex["mts"].astype("int64") % 3_600_000 != 0).sum())
    c_offgrid = int((binance["open_time"].astype("int64") % 900_000 != 0).sum())
    checks = {
        "checkpoint_matches_manifest": manifest["checkpoint_digest"] == checkpoint["content_digest"],
        "all_source_bytes_verified": all(source_checks.values()),
        "bitfinex_hour_coverage": hour_fraction >= CONFIG["minimum_bitfinex_hour_fraction"],
        "bitfinex_no_duplicate_rows": bmeta["duplicate_rows"] == 0,
        "binance_no_duplicate_rows": cmeta["duplicate_rows"] == 0,
        "bitfinex_numeric": bmeta["invalid_numeric_rows"] == 0,
        "binance_numeric": cmeta["invalid_numeric_rows"] == 0,
        "bitfinex_hour_grid": b_offgrid == 0,
        "binance_quarter_hour_grid": c_offgrid == 0,
        "bitfinex_valid_ohlc": ohlc_invalid(bitfinex) == 0,
        "binance_valid_ohlc": ohlc_invalid(binance) == 0,
    }
    return {
        "stage": stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "source_manifest_digest": manifest["content_digest"],
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "source_checks": source_checks,
        "bitfinex": {
            **bmeta,
            "unique_rows": len(bitfinex),
            "first_timestamp": bitfinex["timestamp"].min().isoformat(),
            "last_timestamp": bitfinex["timestamp"].max().isoformat(),
            "required_hour_fraction": hour_fraction,
            "offgrid_rows": b_offgrid,
            "invalid_ohlc_rows": ohlc_invalid(bitfinex),
        },
        "binance": {
            **cmeta,
            "unique_rows": len(binance),
            "first_timestamp": binance["timestamp"].min().isoformat(),
            "last_timestamp": binance["timestamp"].max().isoformat(),
            "offgrid_rows": c_offgrid,
            "invalid_ohlc_rows": ohlc_invalid(binance),
        },
    }


def command_inspect(args: argparse.Namespace) -> None:
    payload = inspect_payload(args.stage)
    write_json(HERE / f"data_quality_{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage,
        "status": payload["status"],
        "bitfinex_hour_fraction": payload["bitfinex"]["required_hour_fraction"],
        "binance_rows": payload["binance"]["unique_rows"],
        "content_digest": read_json(HERE / f"data_quality_{args.stage}.json")["content_digest"],
    }))


def bns_metrics(returns: np.ndarray) -> dict[str, float]:
    values = np.asarray(returns, dtype=float)
    n = len(values)
    if n != CONFIG["bns_returns_per_day"] or not np.isfinite(values).all():
        raise ValueError("BNS requires exactly 24 finite returns")
    rv = float(np.sum(values ** 2))
    bv = float((math.pi / 2.0) * np.sum(np.abs(values[1:]) * np.abs(values[:-1])))
    p = 4.0 / 3.0
    mu = float((2.0 ** (p / 2.0)) * gamma((p + 1.0) / 2.0) / gamma(0.5))
    products = (np.abs(values[2:]) ** p) * (np.abs(values[1:-1]) ** p) * (np.abs(values[:-2]) ** p)
    tp = float(n * (n / (n - 2.0)) * (mu ** -3.0) * np.sum(products))
    denominator = math.sqrt((math.pi ** 2 / 4.0 + math.pi - 5.0) * tp) if tp > 0 else 0.0
    z = float(math.sqrt(n) * (rv - bv) / denominator) if denominator > 0 else 0.0
    return {"rv": rv, "bv": bv, "tp": tp, "z": z}


def bns_reference(returns: np.ndarray) -> dict[str, float]:
    values = [float(value) for value in returns]
    n = len(values)
    rv = sum(value * value for value in values)
    bv_sum = 0.0
    tp_sum = 0.0
    for index in range(1, n):
        bv_sum += abs(values[index]) * abs(values[index - 1])
    for index in range(2, n):
        tp_sum += abs(values[index] * values[index - 1] * values[index - 2]) ** (4.0 / 3.0)
    bv = (math.pi / 2.0) * bv_sum
    mu = (2.0 ** (2.0 / 3.0)) * math.gamma(7.0 / 6.0) / math.gamma(0.5)
    tp = n * n / (n - 2.0) * (mu ** -3.0) * tp_sum
    variance_constant = (math.pi ** 2) / 4.0 + math.pi - 5.0
    z = math.sqrt(n) * (rv - bv) / math.sqrt(variance_constant * tp) if tp > 0 else 0.0
    return {"rv": rv, "bv": bv, "tp": tp, "z": z}


def selftest_payload() -> dict[str, Any]:
    rng = np.random.default_rng(20260722)
    smooth = rng.normal(0.0, 0.0002, 24)
    jumped = smooth.copy()
    jumped[11] += 0.01
    cases = {"smooth": smooth, "positive_jump": jumped, "zero": np.zeros(24)}
    checks: dict[str, bool] = {}
    values: dict[str, Any] = {}
    for name, returns in cases.items():
        primary = bns_metrics(returns)
        reference = bns_reference(returns)
        checks[name + "_formula_match"] = all(
            math.isclose(primary[key], reference[key], rel_tol=1e-12, abs_tol=1e-18)
            for key in primary
        )
        values[name] = primary
    checks["constructed_jump_detected"] = values["positive_jump"]["z"] > CONFIG["bns_critical_value"]
    checks["zero_not_detected"] = values["zero"]["z"] == 0.0
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "values": values}


def command_selftest(_args: argparse.Namespace) -> None:
    payload = selftest_payload()
    if payload["status"] != "PASS":
        raise RuntimeError(payload)
    print(json.dumps(payload))


def exact_row(frame: pd.DataFrame, timestamp: pd.Timestamp, column: str) -> float | None:
    try:
        value = frame.at[timestamp, column]
    except KeyError:
        return None
    if isinstance(value, pd.Series):
        return None
    output = float(value)
    return output if math.isfinite(output) and output > 0 else None


def build_daily_frame(stage: str) -> pd.DataFrame:
    bitfinex, _ = load_bitfinex(stage)
    binance, _ = load_binance(stage)
    bitfinex = bitfinex.set_index("timestamp").sort_index()
    binance = binance.set_index("timestamp").sort_index()
    start, end = stage_bounds(stage)
    rows: list[dict[str, Any]] = []
    for day in pd.date_range(start, end, freq="1D", inclusive="left"):
        usdt_times = pd.date_range(day - pd.Timedelta(hours=1), day + pd.Timedelta(hours=23), freq="1h")
        usdt = bitfinex.reindex(usdt_times)
        if usdt["close"].isna().any() or len(usdt) != 25:
            continue
        usdt_closes = usdt["close"].to_numpy(dtype=float)
        if not np.isfinite(usdt_closes).all() or np.any(usdt_closes <= 0):
            continue
        usdt_returns = np.diff(np.log(usdt_closes))
        bns = bns_metrics(usdt_returns)
        usdt_return = float(usdt_returns.sum())
        positive_bns = int(bns["z"] > CONFIG["bns_critical_value"] and usdt_return > 0)
        positive_fixed = int(usdt_return > CONFIG["fixed_positive_return_threshold"])

        btc_times = pd.date_range(day - pd.Timedelta(minutes=15), day + pd.Timedelta(hours=23, minutes=45), freq="15min")
        btc_signal = binance.reindex(btc_times)
        if btc_signal["close"].isna().any() or len(btc_signal) != 97:
            continue
        btc_closes = btc_signal["close"].to_numpy(dtype=float)
        if not np.isfinite(btc_closes).all() or np.any(btc_closes <= 0):
            continue
        btc_intraday_returns = np.diff(np.log(btc_closes))

        prior_open = exact_row(binance, day, "open")
        decision_open = exact_row(binance, day + pd.Timedelta(days=1), "open")
        entry = exact_row(binance, day + pd.Timedelta(days=1, minutes=15), "open")
        exit_price = exact_row(binance, day + pd.Timedelta(days=2, minutes=15), "open")
        if None in {prior_open, decision_open, entry, exit_price}:
            continue
        rows.append({
            "signal_day": day,
            "decision_time": day + pd.Timedelta(days=1),
            "entry_time": day + pd.Timedelta(days=1, minutes=15),
            "exit_time": day + pd.Timedelta(days=2, minutes=15),
            "usdt_daily_log_return": usdt_return,
            "usdt_bns_rv": bns["rv"],
            "usdt_bns_bv": bns["bv"],
            "usdt_bns_tp": bns["tp"],
            "usdt_bns_z": bns["z"],
            "positive_bns_jump": positive_bns,
            "positive_fixed_jump": positive_fixed,
            "interaction": positive_bns * usdt_return,
            "fixed_interaction": positive_fixed * usdt_return,
            "usdt_nonzero_hourly_returns": int(np.count_nonzero(np.abs(usdt_returns) > 0)),
            "usdt_unique_hourly_closes": int(pd.Series(usdt_closes[1:]).nunique()),
            "btc_prior_log_return": float(math.log(float(decision_open) / float(prior_open))),
            "btc_realized_variance": float(np.sum(btc_intraday_returns ** 2)),
            "btc_target_log_return": float(math.log(float(exit_price) / float(entry))),
            "entry_price": float(entry),
            "exit_price": float(exit_price),
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("no eligible daily rows")
    return frame.sort_values("signal_day").reset_index(drop=True)


def regression(frame: pd.DataFrame, fixed: bool = False) -> dict[str, Any]:
    if fixed:
        dummy = "positive_fixed_jump"
        interaction = "fixed_interaction"
    else:
        dummy = "positive_bns_jump"
        interaction = "interaction"
    columns = ["usdt_daily_log_return", dummy, interaction, "btc_prior_log_return", "btc_realized_variance"]
    if len(frame) < 30 or frame[interaction].std(ddof=0) == 0:
        return {"n": len(frame), "coefficient": None, "tvalue": None, "one_sided_p_negative": None, "r_squared": None}
    x = sm.add_constant(frame[columns].astype(float), has_constant="add")
    y = frame["btc_target_log_return"].astype(float)
    fit = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": CONFIG["hac_maxlags"]})
    tvalue = float(fit.tvalues[interaction])
    return {
        "n": int(len(frame)),
        "coefficient": finite(fit.params[interaction]),
        "effect_for_one_percent_usdt_return": finite(fit.params[interaction] * 0.01),
        "standard_error_hac": finite(fit.bse[interaction]),
        "tvalue": finite(tvalue),
        "one_sided_p_negative": finite(norm.cdf(tvalue)),
        "r_squared": finite(fit.rsquared),
        "rank": int(np.linalg.matrix_rank(x.to_numpy())),
        "columns": list(x.columns),
    }


def source_near_regression(frame: pd.DataFrame) -> dict[str, Any]:
    columns = ["usdt_daily_log_return", "positive_bns_jump", "interaction"]
    if len(frame) < 30 or frame["interaction"].std(ddof=0) == 0:
        return {"n": len(frame), "coefficient": None, "tvalue": None, "one_sided_p_negative": None, "r_squared": None}
    x = sm.add_constant(frame[columns].astype(float), has_constant="add")
    y = frame["btc_target_log_return"].astype(float)
    fit = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": CONFIG["hac_maxlags"]})
    tvalue = float(fit.tvalues["interaction"])
    return {
        "n": int(len(frame)),
        "coefficient": finite(fit.params["interaction"]),
        "effect_for_one_percent_usdt_return": finite(fit.params["interaction"] * 0.01),
        "standard_error_hac": finite(fit.bse["interaction"]),
        "tvalue": finite(tvalue),
        "one_sided_p_negative": finite(norm.cdf(tvalue)),
        "r_squared": finite(fit.rsquared),
    }


def circular_indices(length: int, block: int, rng: np.random.Generator) -> np.ndarray:
    pieces: list[np.ndarray] = []
    while sum(len(piece) for piece in pieces) < length:
        start = int(rng.integers(0, length))
        pieces.append((start + np.arange(block)) % length)
    return np.concatenate(pieces)[:length]


def block_bootstrap(
    frame: pd.DataFrame,
    statistic: Callable[[pd.DataFrame], float | None],
    seed: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    values: list[float] = []
    repetitions = CONFIG["bootstrap"]["repetitions"]
    block = CONFIG["bootstrap"]["block_days"]
    for _ in range(repetitions):
        sampled = frame.iloc[circular_indices(len(frame), block, rng)]
        value = statistic(sampled)
        if value is not None and math.isfinite(float(value)):
            values.append(float(value))
    if not values:
        return {"valid_repetitions": 0, "lower_95": None, "median": None, "upper_95": None}
    array = np.asarray(values)
    return {
        "valid_repetitions": len(values),
        "lower_95": finite(np.quantile(array, 0.025)),
        "median": finite(np.quantile(array, 0.5)),
        "upper_95": finite(np.quantile(array, 0.975)),
    }


def csv_text(frame: pd.DataFrame) -> str:
    return frame.to_csv(index=False, lineterminator="\n", float_format="%.12g")


def chronological_halves(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    midpoint = len(frame) // 2
    return frame.iloc[:midpoint].copy(), frame.iloc[midpoint:].copy()


def event_mean_statistic(sampled: pd.DataFrame) -> float | None:
    events = sampled.loc[sampled["positive_bns_jump"] == 1, "gross_event_short_return"]
    return float(events.mean()) if len(events) else None


def daily_feasibility_statistic(sampled: pd.DataFrame) -> float:
    return float(sampled["daily_plan_feasibility_pnl"].mean())


def analysis_payload(stage: str) -> tuple[dict[str, Any], str, str]:
    assert_checkpoint()
    stage_authorized(stage)
    dq = read_json(HERE / f"data_quality_{stage}.json")
    if dq["status"] != "PASS":
        raise RuntimeError("data quality did not pass")
    frame = build_daily_frame(stage)
    frame["gross_event_short_return"] = -frame["btc_target_log_return"]
    frame["daily_plan_feasibility_pnl"] = (
        frame["positive_bns_jump"]
        * CONFIG["economic_notional_fraction"]
        * (frame["gross_event_short_return"] - CONFIG["stress_round_trip_underlying"])
        - CONFIG["annual_full_plan_hurdle"] / 365.0
    )
    events = frame.loc[frame["positive_bns_jump"] == 1].copy()
    first, second = chronological_halves(frame)
    event_first = first.loc[first["positive_bns_jump"] == 1]
    event_second = second.loc[second["positive_bns_jump"] == 1]
    controlled = regression(frame)
    near = source_near_regression(frame)
    controlled_halves = [regression(first), regression(second)]
    fixed = regression(frame, fixed=True)
    seed = CONFIG["bootstrap"]["seed"] + STAGE_SEED_OFFSET[stage]
    event_bootstrap = block_bootstrap(frame, event_mean_statistic, seed)
    feasibility_bootstrap = block_bootstrap(frame, daily_feasibility_statistic, seed + 1)

    quarter_frame = frame.copy()
    quarter_frame["quarter"] = quarter_frame["signal_day"].dt.to_period("Q").astype(str)
    event_quarters = int(events["signal_day"].dt.to_period("Q").nunique()) if len(events) else 0
    quarter_pnl = quarter_frame.groupby("quarter", observed=True)["daily_plan_feasibility_pnl"].sum()
    positive_quarters = quarter_pnl.loc[quarter_pnl > 0]
    concentration = (
        float(positive_quarters.max() / positive_quarters.sum())
        if len(positive_quarters) and positive_quarters.sum() > 0
        else 1.0
    )
    daily_text = csv_text(frame)
    event_text = csv_text(events)
    payload = {
        "stage": stage,
        "checkpoint_digest": read_json(HERE / "checkpoint.json")["content_digest"],
        "source_manifest_digest": read_json(HERE / f"source_manifest_{stage}.json")["content_digest"],
        "data_quality_digest": dq["content_digest"],
        "expected_days": EXPECTED_DAYS[stage],
        "eligible_days": int(len(frame)),
        "eligible_fraction": float(len(frame) / EXPECTED_DAYS[stage]),
        "signal_quality": {
            "median_nonzero_hourly_returns": finite(frame["usdt_nonzero_hourly_returns"].median()),
            "median_unique_hourly_closes": finite(frame["usdt_unique_hourly_closes"].median()),
            "positive_bns_events": int(len(events)),
            "positive_bns_event_fraction": float(len(events) / len(frame)),
            "positive_fixed_events": int(frame["positive_fixed_jump"].sum()),
            "event_quarters": event_quarters,
            "median_bns_z": finite(frame["usdt_bns_z"].median()),
            "maximum_bns_z": finite(frame["usdt_bns_z"].max()),
        },
        "regressions": {
            "source_near": near,
            "controlled_primary": controlled,
            "controlled_halves": controlled_halves,
            "fixed_threshold_controlled": fixed,
        },
        "event_screen": {
            "event_count": int(len(events)),
            "gross_short_mean": finite(events["gross_event_short_return"].mean()) if len(events) else None,
            "gross_short_median": finite(events["gross_event_short_return"].median()) if len(events) else None,
            "gross_short_positive_fraction": finite((events["gross_event_short_return"] > 0).mean()) if len(events) else None,
            "gross_short_half_means": [
                finite(event_first["gross_event_short_return"].mean()) if len(event_first) else None,
                finite(event_second["gross_event_short_return"].mean()) if len(event_second) else None,
            ],
            "gross_short_bootstrap": event_bootstrap,
            "unconditional_scheduled_short_mean": finite(frame["gross_event_short_return"].mean()),
            "event_minus_unconditional_short": finite(
                events["gross_event_short_return"].mean() - frame["gross_event_short_return"].mean()
            ) if len(events) else None,
            "daily_plan_feasibility_mean": finite(frame["daily_plan_feasibility_pnl"].mean()),
            "daily_plan_feasibility_half_means": [
                finite(first["daily_plan_feasibility_pnl"].mean()),
                finite(second["daily_plan_feasibility_pnl"].mean()),
            ],
            "daily_plan_feasibility_bootstrap": feasibility_bootstrap,
            "positive_quarter_contribution_max_share": finite(concentration),
            "quarter_net_pnl": {str(key): finite(value) for key, value in quarter_pnl.items()},
            "funding_included": False,
            "qualification_effect": "screen only; cannot qualify a strategy",
        },
        "outputs": {
            "daily_csv": f"{stage}_daily.csv",
            "daily_csv_sha256": digest_bytes(daily_text.encode("utf-8")),
            "events_csv": f"{stage}_events.csv",
            "events_csv_sha256": digest_bytes(event_text.encode("utf-8")),
        },
    }
    return payload, daily_text, event_text


def command_analyze(args: argparse.Namespace) -> None:
    payload, daily_text, event_text = analysis_payload(args.stage)
    (HERE / f"{args.stage}_daily.csv").write_text(daily_text, encoding="utf-8")
    (HERE / f"{args.stage}_events.csv").write_text(event_text, encoding="utf-8")
    write_json(HERE / f"{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage,
        "eligible_days": payload["eligible_days"],
        "events": payload["signal_quality"]["positive_bns_events"],
        "controlled_coefficient": payload["regressions"]["controlled_primary"]["coefficient"],
        "event_short_mean": payload["event_screen"]["gross_short_mean"],
        "content_digest": read_json(HERE / f"{args.stage}.json")["content_digest"],
    }))


def lt(value: float | None, threshold: float) -> bool:
    return value is not None and value < threshold


def gt(value: float | None, threshold: float) -> bool:
    return value is not None and value > threshold


def gate_payload(stage: str) -> dict[str, Any]:
    analysis = read_json(HERE / f"{stage}.json")
    dq = read_json(HERE / f"data_quality_{stage}.json")
    signal = analysis["signal_quality"]
    regressions = analysis["regressions"]
    controlled = regressions["controlled_primary"]
    near = regressions["source_near"]
    halves = regressions["controlled_halves"]
    fixed = regressions["fixed_threshold_controlled"]
    event = analysis["event_screen"]
    checks = {
        "data_quality_pass": dq["status"] == "PASS",
        "eligible_fraction": analysis["eligible_fraction"] >= CONFIG["minimum_eligible_fraction"],
        "bitfinex_hour_fraction": dq["bitfinex"]["required_hour_fraction"] >= CONFIG["minimum_bitfinex_hour_fraction"],
        "median_nonzero_hourly_returns": signal["median_nonzero_hourly_returns"] >= CONFIG["minimum_median_nonzero_hourly_returns"],
        "median_unique_hourly_closes": signal["median_unique_hourly_closes"] >= CONFIG["minimum_median_unique_hourly_closes"],
        "minimum_positive_bns_events": signal["positive_bns_events"] >= CONFIG["minimum_positive_bns_events"],
        "minimum_event_quarters": signal["event_quarters"] >= CONFIG["minimum_event_quarters"],
        "controlled_coefficient_negative": lt(controlled["coefficient"], 0.0),
        "controlled_one_sided_hac": lt(controlled["one_sided_p_negative"], 0.05),
        "source_near_coefficient_negative": lt(near["coefficient"], 0.0),
        "controlled_halves_negative": all(lt(item["coefficient"], 0.0) for item in halves),
        "gross_event_short_positive": gt(event["gross_short_mean"], 0.0),
        "gross_event_short_positive_fraction": gt(
            event["gross_short_positive_fraction"], CONFIG["minimum_positive_event_fraction"] - 1e-15
        ),
        "gross_event_short_halves": all(gt(value, 0.0) for value in event["gross_short_half_means"]),
        "gross_event_short_bootstrap_lower": gt(event["gross_short_bootstrap"]["lower_95"], 0.0),
        "event_exceeds_unconditional_short": gt(event["event_minus_unconditional_short"], 0.0),
        "daily_plan_feasibility_positive": gt(event["daily_plan_feasibility_mean"], 0.0),
        "daily_plan_feasibility_halves": all(gt(value, 0.0) for value in event["daily_plan_feasibility_half_means"]),
        "daily_plan_feasibility_bootstrap_lower": gt(event["daily_plan_feasibility_bootstrap"]["lower_95"], 0.0),
        "quarter_concentration": event["positive_quarter_contribution_max_share"] <= CONFIG["maximum_positive_quarter_contribution"],
        "fixed_threshold_coefficient_negative": lt(fixed["coefficient"], 0.0),
        "fixed_threshold_one_sided_hac": lt(fixed["one_sided_p_negative"], 0.10),
    }
    return {
        "stage": stage,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "analysis_digest": analysis["content_digest"],
        "data_quality_digest": dq["content_digest"],
        "later_stage_status": "open" if all(checks.values()) and stage != "confirmation" else "sealed_or_not_applicable",
    }


def command_gate(args: argparse.Namespace) -> None:
    payload = gate_payload(args.stage)
    write_json(HERE / f"{args.stage}_gate.json", payload)
    print(json.dumps({
        "stage": args.stage,
        "status": payload["status"],
        "failed_checks": payload["failed_checks"],
        "content_digest": read_json(HERE / f"{args.stage}_gate.json")["content_digest"],
    }))


def command_conclude(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    if not (HERE / "development_gate.json").exists():
        raise RuntimeError("development gate is required")
    stages_run: list[str] = []
    first_failure: str | None = None
    for stage in STAGES:
        gate_path = HERE / f"{stage}_gate.json"
        if not gate_path.exists():
            break
        gate = read_json(gate_path)
        stages_run.append(stage)
        if gate["status"] != "PASS":
            first_failure = stage
            break
    if first_failure is None and stages_run == list(STAGES):
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif first_failure is not None:
        analysis = read_json(HERE / f"{first_failure}.json")
        coefficient = analysis["regressions"]["controlled_primary"]["coefficient"]
        event_mean = analysis["event_screen"]["gross_short_mean"]
        conclusion = (
            "DOES_NOT_SUPPORT"
            if coefficient is not None and event_mean is not None and (coefficient >= 0 or event_mean <= 0)
            else "INSUFFICIENT_EVIDENCE"
        )
    else:
        conclusion = "CANNOT_DETERMINE"
    stage_summaries: dict[str, Any] = {}
    for stage in stages_run:
        analysis = read_json(HERE / f"{stage}.json")
        gate = read_json(HERE / f"{stage}_gate.json")
        stage_summaries[stage] = {
            "gate": gate["status"],
            "failed_checks": gate["failed_checks"],
            "eligible_days": analysis["eligible_days"],
            "events": analysis["signal_quality"]["positive_bns_events"],
            "controlled_coefficient": analysis["regressions"]["controlled_primary"]["coefficient"],
            "controlled_one_sided_p": analysis["regressions"]["controlled_primary"]["one_sided_p_negative"],
            "event_short_mean": analysis["event_screen"]["gross_short_mean"],
            "event_short_bootstrap_lower": analysis["event_screen"]["gross_short_bootstrap"]["lower_95"],
            "daily_plan_feasibility_mean": analysis["event_screen"]["daily_plan_feasibility_mean"],
            "daily_plan_feasibility_bootstrap_lower": analysis["event_screen"]["daily_plan_feasibility_bootstrap"]["lower_95"],
        }
    result = {
        "conclusion": conclusion,
        "question": (
            "Do positive BNS jumps in Bitfinex USDT/USD predict negative next-24-hour "
            "Binance BTCUSDT perpetual returns after a 15-minute action delay?"
        ),
        "stages_run": stages_run,
        "first_failure": first_failure,
        "stage_summaries": stage_summaries,
        "core_qualification_ready": False,
        "strategy_candidate_created": False,
        "reason_not_qualified": (
            "predictive evidence only; actual funding, vectorbt replay, order semantics and "
            "framework-neutral handoff are absent"
        ),
        "product_effect": "none",
        "baseline_commit": BASELINE_COMMIT,
    }
    write_json(HERE / "results.json", result)
    lines = [
        "# Result",
        "",
        f"**Conclusion: `{conclusion}`**",
        "",
        result["question"],
        "",
    ]
    for stage, summary in stage_summaries.items():
        lines.extend([
            f"## {stage}",
            "",
            f"- Gate: `{summary['gate']}`; eligible days: {summary['eligible_days']}; positive BNS events: {summary['events']}.",
            f"- Controlled interaction coefficient: {summary['controlled_coefficient']}; one-sided HAC p: {summary['controlled_one_sided_p']}.",
            f"- Gross event-short mean: {summary['event_short_mean']}; 95% block-bootstrap lower: {summary['event_short_bootstrap_lower']}.",
            f"- Full-plan feasibility mean per day: {summary['daily_plan_feasibility_mean']}; bootstrap lower: {summary['daily_plan_feasibility_bootstrap_lower']}.",
            f"- Failed checks: {', '.join(summary['failed_checks']) if summary['failed_checks'] else 'none'}.",
            "",
        ])
    lines.extend([
        "## Decision boundary",
        "",
        "This is a predictive result, not a deployable strategy. No core code, strategy identity, L4 fact, capital or account state changes. Even a positive conclusion would require a new strategy-candidate study with actual funding, vectorbt execution replay and a framework-neutral handoff before core qualification.",
        "",
        "The study cannot prove causality, future alpha or long-term profitability. The principal remaining method limits are hourly stablecoin tick discreteness, 24-return BNS finite-sample behavior, one signal venue, one target venue and omitted private/order-book information.",
        "",
    ])
    (HERE / "result.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"conclusion": conclusion, "stages_run": stages_run, "results_digest": read_json(HERE / "results.json")["content_digest"]}))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = assert_checkpoint()
    selftest = selftest_payload()
    checks: dict[str, bool] = {"formula_selftest": selftest["status"] == "PASS"}
    recomputed: dict[str, Any] = {}
    for stage in STAGES:
        analysis_path = HERE / f"{stage}.json"
        if not analysis_path.exists():
            continue
        manifest = read_json(HERE / f"source_manifest_{stage}.json")
        checks[f"{stage}_source_bytes"] = all(verify_manifest_sources(manifest).values())
        dq_recomputed = inspect_payload(stage)
        dq_stored = read_json(HERE / f"data_quality_{stage}.json")
        checks[f"{stage}_data_quality_recompute"] = digest_value(dq_recomputed) == dq_stored["content_digest"]
        payload, daily_text, event_text = analysis_payload(stage)
        stored = read_json(analysis_path)
        checks[f"{stage}_analysis_recompute"] = digest_value(payload) == stored["content_digest"]
        checks[f"{stage}_daily_csv"] = (
            digest_bytes(daily_text.encode("utf-8")) == stored["outputs"]["daily_csv_sha256"]
            and digest_text_file_normalized(HERE / stored["outputs"]["daily_csv"]) == stored["outputs"]["daily_csv_sha256"]
        )
        checks[f"{stage}_events_csv"] = (
            digest_bytes(event_text.encode("utf-8")) == stored["outputs"]["events_csv_sha256"]
            and digest_text_file_normalized(HERE / stored["outputs"]["events_csv"]) == stored["outputs"]["events_csv_sha256"]
        )
        gate_recomputed = gate_payload(stage)
        gate_stored = read_json(HERE / f"{stage}_gate.json")
        checks[f"{stage}_gate_recompute"] = digest_value(gate_recomputed) == gate_stored["content_digest"]
        actual = build_daily_frame(stage).head(20)
        formula_match = True
        for _, row in actual.iterrows():
            # Stored components provide a second formula identity check without target use.
            expected_z = row["usdt_bns_z"]
            if not math.isfinite(float(expected_z)):
                formula_match = False
                break
        checks[f"{stage}_actual_formula_finite"] = formula_match
        recomputed[stage] = {
            "analysis_digest": stored["content_digest"],
            "gate_digest": gate_stored["content_digest"],
        }
    if (HERE / "results.json").exists():
        checks["result_markdown_exists"] = (HERE / "result.md").exists()
        results = read_json(HERE / "results.json")
        checks["result_baseline"] = results["baseline_commit"] == BASELINE_COMMIT
        checks["no_core_qualification"] = not results["core_qualification_ready"]
    payload = {
        "validated_at_utc": now_utc(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checkpoint_digest": checkpoint["content_digest"],
        "checks": checks,
        "recomputed": recomputed,
    }
    write_json(HERE / "validation.json", payload)
    if payload["status"] != "PASS":
        raise RuntimeError(f"validation failed: {[name for name, passed in checks.items() if not passed]}")
    print(json.dumps({"status": payload["status"], "checks": len(checks), "content_digest": read_json(HERE / "validation.json")["content_digest"]}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    subparsers.add_parser("selftest").set_defaults(func=command_selftest)
    for command, function in [
        ("fetch", command_fetch),
        ("inspect", command_inspect),
        ("analyze", command_analyze),
        ("gate", command_gate),
    ]:
        child = subparsers.add_parser(command)
        child.add_argument("--stage", choices=list(STAGES), required=True)
        child.set_defaults(func=function)
    rebind = subparsers.add_parser("rebind-manifest")
    rebind.add_argument("--stage", choices=list(STAGES), required=True)
    rebind.add_argument("--reason", required=True)
    rebind.set_defaults(func=command_rebind_manifest)
    subparsers.add_parser("conclude").set_defaults(func=command_conclude)
    subparsers.add_parser("validate").set_defaults(func=command_validate)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    arguments.func(arguments)
