from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import math
import os
import platform
import time
import urllib.parse
import urllib.request
import urllib.error
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
CACHE_ROOT = Path(os.environ.get(
    "HALPHA_MONTHLY_MAX_CACHE",
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "category-momentum-gated-one-shot-long/2026-07-22-v1",
))
BASE_URL = "https://fapi.binance.com"
ARCHIVE_BASE_URL = "https://data.binance.vision/data/futures/um/monthly"
UNIVERSE_PATH = Path("research/market-universe/universe.csv")
UNIVERSE_SHA256 = "1f24adfb64b7a52a170b730ee7517916b2da8ab45785779dee6be991762186cc"

CATEGORY_MEMBERS: dict[str, list[str]] = {
    "AI": ["CHRUSDT", "GRTUSDT", "LPTUSDT", "RLCUSDT", "THETAUSDT"],
    "DeFi": [
        "1INCHUSDT", "AAVEUSDT", "ANKRUSDT", "BANDUSDT", "BELUSDT", "C98USDT",
        "COMPUSDT", "CRVUSDT", "DYDXUSDT", "KAVAUSDT", "KNCUSDT", "OGNUSDT",
        "RSRUSDT", "RUNEUSDT", "SNXUSDT", "SUSHIUSDT", "UNIUSDT", "YFIUSDT", "ZRXUSDT",
    ],
    "Infrastructure": [
        "ARPAUSDT", "BATUSDT", "ENSUSDT", "GTCUSDT", "IOTXUSDT", "LINKUSDT",
        "MASKUSDT", "MTLUSDT", "SFPUSDT", "TRBUSDT",
    ],
    "Layer-1": [
        "ADAUSDT", "ALGOUSDT", "ATOMUSDT", "AVAXUSDT", "BNBUSDT", "CELOUSDT",
        "DOTUSDT", "EGLDUSDT", "HBARUSDT", "ICPUSDT", "ICXUSDT", "IOSTUSDT",
        "KSMUSDT", "NEARUSDT", "NEOUSDT", "QTUMUSDT", "ROSEUSDT", "SOLUSDT",
        "TRXUSDT", "VETUSDT", "XTZUSDT",
    ],
    "Layer-2": ["CELRUSDT", "CTSIUSDT", "ONEUSDT", "SKLUSDT", "XLMUSDT"],
    "Payment": ["1000XECUSDT", "BCHUSDT", "COTIUSDT", "LTCUSDT", "XRPUSDT"],
    "PoW": [
        "DASHUSDT", "ETCUSDT", "IOTAUSDT", "ONTUSDT", "RVNUSDT", "XMRUSDT",
        "ZECUSDT", "ZENUSDT", "ZILUSDT",
    ],
}
SYMBOL_TO_CATEGORY = {
    symbol: category for category, members in CATEGORY_MEMBERS.items() for symbol in members
}
SYMBOLS = sorted(SYMBOL_TO_CATEGORY)
TARGET_SYMBOLS = [
    "1000XECUSDT", "AAVEUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "CRVUSDT",
    "DASHUSDT", "ENSUSDT", "ETCUSDT", "HBARUSDT", "KAVAUSDT",
    "LINKUSDT", "LTCUSDT", "NEARUSDT", "RUNEUSDT", "SNXUSDT", "SOLUSDT",
    "TRXUSDT", "UNIUSDT", "VETUSDT", "XLMUSDT", "XMRUSDT", "XRPUSDT",
    "ZECUSDT", "ZILUSDT",
]

STAGES = {
    "development": {
        "fetch_start": "2021-11-17T00:00:00Z",
        "start": "2022-01-01T00:00:00Z",
        "end_exclusive": "2024-01-01T00:00:00Z",
    },
    "evaluation": {
        "fetch_start": "2023-11-17T00:00:00Z",
        "start": "2024-01-01T00:00:00Z",
        "end_exclusive": "2025-01-01T00:00:00Z",
    },
    "confirmation": {
        "fetch_start": "2024-11-17T00:00:00Z",
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2026-07-01T00:00:00Z",
    },
}

CONFIG = {
    "strategy_id": "RESEARCH_PAST_MONTH_MAX28_TOP3_WEEKLY_ONE_SHOT_LONG_0P5X_V1",
    "direction": "LONG_ONLY",
    "formation_days": 28,
    "hold_days": 7,
    "top_targets": 3,
    "notional_fraction": 0.5,
    "target_min_median_quote_volume_30d": 10_000_000.0,
    "min_rankable_targets": 20,
    "annual_capital_hurdle": 0.04,
    "max_missing_funding_mark_fraction": 0.005,
    "max_excluded_trade_fraction": 0.02,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "long_funding_stress": {"positive_cost_multiplier": 1.5, "negative_benefit_multiplier": 0.5},
    "diagnostics": {
        "max21": {"kind": "max", "formation_days": 21, "hold_days": 7, "top_targets": 3},
        "max35": {"kind": "max", "formation_days": 35, "hold_days": 7, "top_targets": 3},
        "top5": {"kind": "max", "formation_days": 28, "hold_days": 7, "top_targets": 5},
        "mom28": {"kind": "momentum", "formation_days": 28, "hold_days": 7, "top_targets": 3},
        "last1": {"kind": "last_return", "formation_days": 1, "hold_days": 7, "top_targets": 3},
        "scheduled_long": {"kind": "scheduled_long", "formation_days": 28, "hold_days": 7, "top_targets": 3},
    },
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_ms(value: str | pd.Timestamp) -> int:
    return int(pd.Timestamp(value).timestamp() * 1000)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def request_json(endpoint: str, params: dict[str, Any]) -> tuple[bytes, str]:
    url = f"{BASE_URL}{endpoint}?{urllib.parse.urlencode(params)}"
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Halpha-Research/1.0"})
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
            json.loads(raw)
            return raw, url
        except urllib.error.HTTPError as exc:
            last_error = exc
            if attempt < 4:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if exc.code in {403, 418, 429}:
                    delay = min(45.0, float(retry_after) if retry_after else 10.0 * (attempt + 1))
                else:
                    delay = 1.5 * (attempt + 1)
                time.sleep(delay)
        except Exception as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def validate_universe_snapshot() -> None:
    if not UNIVERSE_PATH.exists() or sha256_file(UNIVERSE_PATH).lower() != UNIVERSE_SHA256:
        raise RuntimeError("frozen market-universe input is missing or changed")
    frame = pd.read_csv(UNIVERSE_PATH, dtype=str, keep_default_na=False)
    rows = frame[frame["symbol"].isin(SYMBOLS)].copy()
    if set(rows["symbol"]) != set(SYMBOLS):
        raise RuntimeError("frozen market-universe does not contain all fixed symbols")
    actual = dict(zip(rows["symbol"], rows["classification_subtypes"], strict=True))
    if actual != SYMBOL_TO_CATEGORY:
        raise RuntimeError("fixed category membership differs from frozen market-universe")


def command_checkpoint(_args: argparse.Namespace) -> None:
    validate_universe_snapshot()
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {"id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1", "instrument": "BTCUSDT-PERP"},
        "research_kind": "STRATEGY_CANDIDATE",
        "question": (
            "Does a high past-month maximum daily return predict enough next-week continuation among "
            "liquid current Binance perpetual targets to support a weekly LONG one-shot plan after "
            "retail costs, actual funding, capital hurdle, simple baselines, and sequential time evidence?"
        ),
        "evidence_boundary": (
            "Constituent price periods and related cumulative-momentum results are exposed. This exact "
            "past-month maximum-daily-return conversion and its outcomes are unviewed. The fixed target "
            "list is a current-survivor rather than point-in-time market universe."
        ),
        "universe": {
            "path": str(UNIVERSE_PATH), "sha256": UNIVERSE_SHA256,
            "snapshot_time_utc": "2026-07-21T06:42:30Z",
            "categories": CATEGORY_MEMBERS, "symbol_count": len(SYMBOLS),
            "target_symbols": TARGET_SYMBOLS, "target_symbol_count": len(TARGET_SYMBOLS),
        },
        "stages": STAGES,
        "config": CONFIG,
        "stage_open_rule": "development -> evaluation -> confirmation; next-stage download forbidden unless prior gate PASS",
        "allowed_fixes": (
            "retrieval, parsing, identity, completeness, deterministic statistics, or implementation defects only; "
            "no signal, universe, cost, gate, period, baseline, or parameter changes after checkpoint"
        ),
        "forbidden_after_checkpoint": [
            "selecting a favorable target, direction, MAX lookback, holding period or rank cutoff",
            "lowering costs or capital hurdle", "opening a later stage after gate failure",
            "treating the current target list or classifications as historical point-in-time facts",
        ],
        "files": {
            "study_py_sha256": sha256_file(Path(__file__)),
            "preregistration_sha256": sha256_file(HERE / "preregistration.md"),
            "sources_sha256": sha256_file(HERE / "sources.md"),
        },
        "environment": {
            "python": platform.python_version(), "vectorbt": vbt.__version__,
            "pandas": pd.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
        },
        "cache_root": str(CACHE_ROOT),
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"checkpoint": str(HERE / "checkpoint.json"), "digest": payload["content_digest"]}))


def ensure_checkpoint() -> dict[str, Any]:
    checkpoint = read_json(HERE / "checkpoint.json")
    if checkpoint["config"] != CONFIG or checkpoint["universe"]["categories"] != CATEGORY_MEMBERS or checkpoint["universe"]["target_symbols"] != TARGET_SYMBOLS:
        raise RuntimeError("checkpoint differs from fixed code configuration")
    validate_universe_snapshot()
    return checkpoint


def prior_stage(stage: str) -> str | None:
    return {"evaluation": "development", "confirmation": "evaluation"}.get(stage)


def stage_authorized(stage: str) -> None:
    prior = prior_stage(stage)
    if prior:
        gate_path = HERE / f"{prior}_gate.json"
        if not gate_path.exists() or read_json(gate_path)["status"] != "PASS":
            raise RuntimeError(f"{stage} is sealed because {prior} gate is not PASS")


def stage_kline_end(stage: str) -> pd.Timestamp:
    return pd.Timestamp(STAGES[stage]["end_exclusive"]) + pd.Timedelta(days=1)


def fetch_pages(
    endpoint: str,
    base_params: dict[str, Any],
    time_key: str,
    limit: int,
    start: pd.Timestamp,
    end_exclusive: pd.Timestamp,
    out_dir: Path,
) -> list[dict[str, Any]]:
    cursor = utc_ms(start)
    end_ms = utc_ms(end_exclusive)
    pages: list[dict[str, Any]] = []
    page_number = 0
    while cursor < end_ms:
        params = dict(base_params)
        params.update({"startTime": cursor, "endTime": end_ms - 1, "limit": limit})
        path = out_dir / f"{time_key}-{page_number:03d}.json"
        url = f"{BASE_URL}{endpoint}?{urllib.parse.urlencode(params)}"
        fetched_from_network = False
        if path.exists():
            raw = path.read_bytes()
            json.loads(raw)
        else:
            raw, url = request_json(endpoint, params)
            fetched_from_network = True
        rows = json.loads(raw)
        if not rows:
            break
        first = int(rows[0][0] if isinstance(rows[0], list) else rows[0][time_key])
        last = int(rows[-1][0] if isinstance(rows[-1], list) else rows[-1][time_key])
        if path.exists() and path.read_bytes() != raw:
            raise RuntimeError(f"refusing to overwrite revised raw input: {path}")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        pages.append({
            "url": url, "path": str(path), "bytes": len(raw), "sha256": sha256_bytes(raw),
            "rows": len(rows), "first_time_ms": first, "last_time_ms": last,
        })
        if last + 1 <= cursor:
            raise RuntimeError(f"non-advancing pagination for {endpoint}")
        cursor = last + 1
        page_number += 1
        if fetched_from_network:
            time.sleep(0.30)
    return pages


def month_labels(stage: str) -> list[str]:
    start = pd.Timestamp(STAGES[stage]["start"]).tz_convert(None)
    end = (pd.Timestamp(STAGES[stage]["end_exclusive"]) - pd.Timedelta(days=1)).tz_convert(None)
    return [period.strftime("%Y-%m") for period in pd.period_range(start, end, freq="M")]


def archive_urls(symbol: str, month: str, kind: str) -> tuple[str, str, str]:
    if kind == "fundingRate":
        filename = f"{symbol}-fundingRate-{month}.zip"
        url = f"{ARCHIVE_BASE_URL}/fundingRate/{symbol}/{filename}"
    elif kind == "markPriceKlines":
        filename = f"{symbol}-8h-{month}.zip"
        url = f"{ARCHIVE_BASE_URL}/markPriceKlines/{symbol}/8h/{filename}"
    elif kind == "markPriceKlines1m":
        filename = f"{symbol}-1m-{month}.zip"
        url = f"{ARCHIVE_BASE_URL}/markPriceKlines/{symbol}/1m/{filename}"
    else:
        raise ValueError(kind)
    return filename, url, f"{url}.CHECKSUM"


def request_bytes(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Halpha-Research/1.0"})
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def fetch_archive(task: tuple[str, str, str, str]) -> dict[str, Any]:
    stage, symbol, month, kind = task
    filename, url, checksum_url = archive_urls(symbol, month, kind)
    root = CACHE_ROOT / stage / symbol / "archive" / kind
    zip_path = root / filename
    checksum_path = root / f"{filename}.CHECKSUM"
    if zip_path.exists() and checksum_path.exists():
        zip_bytes = zip_path.read_bytes()
        checksum_bytes = checksum_path.read_bytes()
    else:
        zip_bytes = request_bytes(url)
        checksum_bytes = request_bytes(checksum_url)
        root.mkdir(parents=True, exist_ok=True)
        if zip_path.exists() and zip_path.read_bytes() != zip_bytes:
            raise RuntimeError(f"refusing to overwrite revised archive: {zip_path}")
        if checksum_path.exists() and checksum_path.read_bytes() != checksum_bytes:
            raise RuntimeError(f"refusing to overwrite revised checksum: {checksum_path}")
        if not zip_path.exists():
            zip_path.write_bytes(zip_bytes)
        if not checksum_path.exists():
            checksum_path.write_bytes(checksum_bytes)
    expected = checksum_bytes.decode("utf-8").strip().split()[0].lower()
    actual = sha256_bytes(zip_bytes)
    if actual != expected:
        raise RuntimeError(f"official checksum mismatch: {zip_path}")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise RuntimeError(f"unexpected archive members: {zip_path}")
        csv_bytes = archive.read(names[0])
    return {
        "kind": kind, "month": month, "url": url, "checksum_url": checksum_url,
        "path": str(zip_path), "checksum_path": str(checksum_path),
        "bytes": len(zip_bytes), "sha256": actual, "csv_member": names[0],
        "csv_bytes": len(csv_bytes), "csv_sha256": sha256_bytes(csv_bytes),
    }


def fetch_target_archives(stage: str) -> dict[str, dict[str, list[dict[str, Any]]]]:
    tasks = [
        (stage, symbol, month, kind)
        for symbol in TARGET_SYMBOLS
        for month in month_labels(stage)
        for kind in ["fundingRate", "markPriceKlines"]
    ]
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(fetch_archive, task) for task in tasks]
        for number, future in enumerate(futures, start=1):
            results.append(future.result())
            if number % 200 == 0 or number == len(futures):
                print(json.dumps({"stage": stage, "archive_files": number, "total": len(futures)}))
    output: dict[str, dict[str, list[dict[str, Any]]]] = {
        symbol: {"fundingRate": [], "markPriceKlines": [], "markPriceKlines1m": []}
        for symbol in TARGET_SYMBOLS
    }
    for task, result in zip(tasks, results, strict=True):
        _, symbol, _, kind = task
        output[symbol][kind].append(result)
    gap_tasks = [
        (stage, symbol, month, "markPriceKlines1m")
        for symbol in TARGET_SYMBOLS
        for month in missing_mark_months(
            output[symbol]["fundingRate"], output[symbol]["markPriceKlines"]
        )
    ]
    if gap_tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            gap_futures = [executor.submit(fetch_archive, task) for task in gap_tasks]
            for number, (task, future) in enumerate(zip(gap_tasks, gap_futures, strict=True), start=1):
                result = future.result()
                _, symbol, _, kind = task
                output[symbol][kind].append(result)
                if number % 20 == 0 or number == len(gap_futures):
                    print(json.dumps({
                        "stage": stage, "gap_mark_archives": number, "total": len(gap_futures)
                    }))
    return output


def command_fetch(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    spec = STAGES[args.stage]
    kline_start = pd.Timestamp(spec["fetch_start"])
    kline_end = stage_kline_end(args.stage)
    archives = fetch_target_archives(args.stage)
    manifest: dict[str, Any] = {
        "accessed_at_utc": iso_now(), "stage": args.stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "source": "Binance public USD-M REST; no credentials",
        "periods": {
            "kline_start": str(kline_start), "kline_end_exclusive": str(kline_end),
            "funding_start": spec["start"], "funding_end_exclusive": spec["end_exclusive"],
        },
        "symbols": {},
    }
    for number, symbol in enumerate(SYMBOLS, start=1):
        root = CACHE_ROOT / args.stage / symbol / "raw"
        manifest["symbols"][symbol] = {
            "category": SYMBOL_TO_CATEGORY[symbol],
            "kline_pages": fetch_pages(
                "/fapi/v1/klines", {"symbol": symbol, "interval": "1d"}, "openTime", 1500,
                kline_start, kline_end, root / "klines",
            ),
            "funding_archives": archives[symbol]["fundingRate"] if symbol in archives else [],
            "mark_price_archives": archives[symbol]["markPriceKlines"] if symbol in archives else [],
            "mark_price_gap_archives": archives[symbol]["markPriceKlines1m"] if symbol in archives else [],
        }
        if number % 10 == 0 or number == len(SYMBOLS):
            print(json.dumps({"stage": args.stage, "fetched": number, "total": len(SYMBOLS)}))
    manifest["content_digest"] = canonical_digest(manifest)
    write_json(HERE / f"source_manifest_{args.stage}.json", manifest)
    print(json.dumps({"manifest": str(HERE / f"source_manifest_{args.stage}.json"), "digest": manifest["content_digest"]}))


def load_rows(items: list[dict[str, Any]]) -> list[Any]:
    rows: list[Any] = []
    for item in items:
        path = Path(item["path"])
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or sha256_bytes(raw) != item["sha256"]:
            raise RuntimeError(f"external input identity mismatch: {path}")
        rows.extend(json.loads(raw))
    return rows


def load_archive_member(item: dict[str, Any]) -> bytes:
    path = Path(item["path"])
    raw = path.read_bytes()
    if len(raw) != item["bytes"] or sha256_bytes(raw) != item["sha256"]:
        raise RuntimeError(f"archive identity mismatch: {path}")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        csv_bytes = archive.read(item["csv_member"])
    if len(csv_bytes) != item["csv_bytes"] or sha256_bytes(csv_bytes) != item["csv_sha256"]:
        raise RuntimeError(f"archive CSV identity mismatch: {path}")
    return csv_bytes


def load_mark_archive(item: dict[str, Any], columns: list[str]) -> pd.DataFrame:
    csv_bytes = load_archive_member(item)
    first_token = csv_bytes.splitlines()[0].split(b",", 1)[0].decode("utf-8-sig")
    if first_token == "open_time":
        frame = pd.read_csv(io.BytesIO(csv_bytes))
        if list(frame.columns) != columns:
            raise RuntimeError(f"unexpected mark-price header: {item['path']}")
    else:
        frame = pd.read_csv(io.BytesIO(csv_bytes), header=None, names=columns)
        if frame.shape[1] != len(columns):
            raise RuntimeError(f"unexpected mark-price width: {item['path']}")
    return frame


def missing_mark_months(
    funding_items: list[dict[str, Any]], mark_items: list[dict[str, Any]]
) -> list[str]:
    funding = pd.concat(
        [pd.read_csv(io.BytesIO(load_archive_member(item))) for item in funding_items],
        ignore_index=True,
    ).rename(columns={"calc_time": "fundingTime"})
    funding["fundingTime"] = pd.to_datetime(funding["fundingTime"], unit="ms", utc=True)
    mark_columns = [
        "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
        "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
    ]
    marks = pd.concat([load_mark_archive(item, mark_columns) for item in mark_items], ignore_index=True)
    marks["open_time"] = pd.to_datetime(marks["open_time"], unit="ms", utc=True)
    matched = pd.merge_asof(
        funding[["fundingTime"]].sort_values("fundingTime"),
        marks[["open_time"]].drop_duplicates().sort_values("open_time"),
        left_on="fundingTime", right_on="open_time", direction="nearest",
        tolerance=pd.Timedelta(minutes=1),
    )
    return sorted({timestamp.strftime("%Y-%m") for timestamp in matched.loc[
        matched["open_time"].isna(), "fundingTime"
    ]})


def load_symbol(stage: str, symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    item = read_json(HERE / f"source_manifest_{stage}.json")["symbols"][symbol]
    bars = pd.DataFrame(load_rows(item["kline_pages"]), columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
        "trade_count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
    ])
    if bars.empty:
        raise RuntimeError(f"no kline data: {stage} {symbol}")
    bars["open_time"] = pd.to_datetime(bars["open_time"], unit="ms", utc=True)
    for column in ["open", "high", "low", "close", "volume", "quote_volume"]:
        bars[column] = pd.to_numeric(bars[column], errors="raise")
    bars = bars.drop_duplicates("open_time", keep="last").sort_values("open_time").set_index("open_time")

    if not item["funding_archives"]:
        funding = pd.DataFrame(columns=["fundingTime", "fundingRate", "markPrice"])
    else:
        funding_parts = [pd.read_csv(io.BytesIO(load_archive_member(archive))) for archive in item["funding_archives"]]
        funding = pd.concat(funding_parts, ignore_index=True)
        funding = funding.rename(columns={"calc_time": "fundingTime", "last_funding_rate": "fundingRate"})
        funding["fundingTime"] = pd.to_datetime(funding["fundingTime"], unit="ms", utc=True)
        funding["fundingRate"] = pd.to_numeric(funding["fundingRate"], errors="raise")
        mark_columns = [
            "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
            "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
        ]
        mark_parts = [
            load_mark_archive(archive, mark_columns)
            for archive in item["mark_price_archives"] + item.get("mark_price_gap_archives", [])
        ]
        marks = pd.concat(mark_parts, ignore_index=True)
        marks["open_time"] = pd.to_datetime(marks["open_time"], unit="ms", utc=True)
        marks["open"] = pd.to_numeric(marks["open"], errors="raise")
        marks = marks.drop_duplicates("open_time", keep="last").sort_values("open_time")
        funding = pd.merge_asof(
            funding.sort_values("fundingTime"), marks[["open_time", "open"]],
            left_on="fundingTime", right_on="open_time", direction="nearest", tolerance=pd.Timedelta(minutes=1),
        ).rename(columns={"open": "markPrice"})
        funding = funding.drop_duplicates("fundingTime", keep="last").sort_values("fundingTime")
    funding = funding.set_index("fundingTime").sort_index()
    return bars, funding


def load_all(stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    bars: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        bars[symbol], funding[symbol] = load_symbol(stage, symbol)
    return bars, funding


def command_inspect(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    stage_authorized(args.stage)
    bars, funding = load_all(args.stage)
    spec = STAGES[args.stage]
    fetch_start = pd.Timestamp(spec["fetch_start"])
    expected_end = pd.Timestamp(spec["end_exclusive"])
    payload: dict[str, Any] = {"checked_at_utc": iso_now(), "stage": args.stage, "status": "PASS", "symbols": {}}
    for symbol in SYMBOLS:
        frame = bars[symbol]
        first_midnight = max(fetch_start, frame.index.min().ceil("D"))
        expected = pd.date_range(first_midnight, expected_end, freq="1D", inclusive="both")
        observed = frame[(frame.index >= first_midnight) & (frame.index <= expected_end)]
        missing = expected.difference(observed.index)
        invalid_ohlc = int(((observed[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
        invalid_range = int(((observed["high"] < observed[["open", "close"]].max(axis=1)) | (observed["low"] > observed[["open", "close"]].min(axis=1))).sum())
        invalid_volume = int((observed[["volume", "quote_volume"]] < 0).any(axis=1).sum())
        rates = funding[symbol]
        funding_required = symbol in TARGET_SYMBOLS
        missing_mark = int(rates["markPrice"].isna().sum()) if not rates.empty else 0
        missing_mark_fraction = float(missing_mark / len(rates)) if len(rates) else (1.0 if funding_required else 0.0)
        max_gap_hours = float(rates.index.to_series().diff().dt.total_seconds().max() / 3600.0) if len(rates) > 1 else (math.inf if funding_required else 0.0)
        funding_ok = (
            len(rates) > 0
            and missing_mark_fraction <= float(CONFIG["max_missing_funding_mark_fraction"])
            and max_gap_hours <= 25.0
        ) if funding_required else len(rates) == 0
        status = "PASS" if len(missing) == 0 and invalid_ohlc == 0 and invalid_range == 0 and invalid_volume == 0 and funding_ok else "FAIL"
        if status != "PASS":
            payload["status"] = "FAIL"
        payload["symbols"][symbol] = {
            "status": status, "bars": int(len(observed)), "first_bar": str(frame.index.min()),
            "missing_daily_bars": int(len(missing)), "invalid_ohlc": invalid_ohlc,
            "invalid_range": invalid_range, "invalid_volume": invalid_volume,
            "funding_rows": int(len(rates)), "missing_funding_mark_price": missing_mark,
            "missing_funding_mark_fraction": missing_mark_fraction,
            "max_funding_gap_hours": max_gap_hours, "funding_required_for_target": funding_required,
        }
    payload["manifest_sha256"] = sha256_file(HERE / f"source_manifest_{args.stage}.json")
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / f"data_quality_{args.stage}.json", payload)
    print(json.dumps({"stage": args.stage, "status": payload["status"]}))


def make_matrices(bars: dict[str, pd.DataFrame], stage: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spec = STAGES[stage]
    index = pd.date_range(pd.Timestamp(spec["fetch_start"]), pd.Timestamp(spec["end_exclusive"]), freq="1D", inclusive="both")
    opens = pd.DataFrame(index=index, columns=SYMBOLS, dtype=float)
    closes = opens.copy()
    quote_volume = opens.copy()
    for symbol in SYMBOLS:
        opens[symbol] = bars[symbol]["open"].reindex(index)
        closes[symbol] = bars[symbol]["close"].reindex(index)
        quote_volume[symbol] = bars[symbol]["quote_volume"].reindex(index)
    return opens, closes, quote_volume


def adjusted_long_funding_rate(rate: float) -> float:
    if rate > 0:
        return rate * float(CONFIG["long_funding_stress"]["positive_cost_multiplier"])
    return rate * float(CONFIG["long_funding_stress"]["negative_benefit_multiplier"])


def signal_at(
    kind: str,
    target: str,
    decision: pd.Timestamp,
    feature: pd.DataFrame,
    median_volume: pd.DataFrame,
    top_targets: int,
) -> tuple[bool, dict[str, Any]]:
    target_feature = feature.at[decision, target] if target in feature.columns else np.nan
    target_volume = median_volume.at[decision, target]
    common = {
        "feature_value": None if pd.isna(target_feature) else float(target_feature),
        "target_median_quote_volume_30d": None if pd.isna(target_volume) else float(target_volume),
        "feature_rank": None, "rankable_targets": 0,
    }
    if pd.isna(target_volume) or float(target_volume) < float(CONFIG["target_min_median_quote_volume_30d"]):
        return False, common
    eligible: list[tuple[float, str]] = []
    for symbol in TARGET_SYMBOLS:
        med = median_volume.at[decision, symbol]
        value = feature.at[decision, symbol] if symbol in feature.columns else np.nan
        if pd.notna(med) and float(med) >= float(CONFIG["target_min_median_quote_volume_30d"]):
            if kind == "scheduled_long":
                eligible.append((0.0, symbol))
            elif pd.notna(value):
                eligible.append((float(value), symbol))
    common["rankable_targets"] = len(eligible)
    if len(eligible) < int(CONFIG["min_rankable_targets"]):
        return False, common
    if kind == "scheduled_long":
        return True, common
    ranking = [symbol for _value, symbol in sorted(eligible, key=lambda row: (-row[0], row[1]))]
    if target not in ranking:
        return False, common
    rank = ranking.index(target) + 1
    common["feature_rank"] = rank
    return rank <= top_targets, common


def build_trades(
    stage: str,
    bars: dict[str, pd.DataFrame],
    funding: dict[str, pd.DataFrame],
    kind: str,
    formation_days: int,
    hold_days: int,
    top_targets: int = 3,
) -> tuple[pd.DataFrame, int]:
    opens, closes, quote_volume = make_matrices(bars, stage)
    daily_returns = closes.pct_change(fill_method=None)
    if kind == "max":
        feature = daily_returns.rolling(formation_days, min_periods=formation_days).max()
    elif kind == "momentum":
        feature = closes / closes.shift(formation_days) - 1.0
    elif kind == "last_return":
        feature = daily_returns
    elif kind == "scheduled_long":
        feature = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    else:
        raise ValueError(f"unsupported signal kind: {kind}")
    median_volume = quote_volume.rolling(30, min_periods=30).median()
    start = pd.Timestamp(STAGES[stage]["start"])
    end = pd.Timestamp(STAGES[stage]["end_exclusive"])
    last_decision = end - pd.Timedelta(days=hold_days + 1)
    all_decisions = pd.date_range(start, last_decision, freq="1D", inclusive="both")
    decisions = all_decisions[all_decisions.dayofweek == 6]
    rows: list[dict[str, Any]] = []
    excluded_missing_funding = 0
    for symbol in TARGET_SYMBOLS:
        next_entry_after = start
        for decision in decisions:
            entry = decision + pd.Timedelta(days=1)
            exit_time = entry + pd.Timedelta(days=hold_days)
            if entry < next_entry_after:
                continue
            entry_price = opens.at[entry, symbol] if entry in opens.index else np.nan
            exit_price = opens.at[exit_time, symbol] if exit_time in opens.index else np.nan
            if pd.isna(entry_price) or pd.isna(exit_price) or float(entry_price) <= 0 or float(exit_price) <= 0:
                continue
            active, diagnostics = signal_at(kind, symbol, decision, feature, median_volume, top_targets)
            if not active:
                continue
            entry_price = float(entry_price)
            exit_price = float(exit_price)
            quantity = float(CONFIG["notional_fraction"]) / entry_price
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index < exit_time)]
            if rates["markPrice"].isna().any():
                excluded_missing_funding += 1
                next_entry_after = exit_time + pd.Timedelta(days=1)
                continue
            actual_funding = float((-quantity * rates["markPrice"] * rates["fundingRate"]).sum())
            stressed_rates = rates["fundingRate"].map(adjusted_long_funding_rate)
            stress_funding = float((-quantity * rates["markPrice"] * stressed_rates).sum())
            rows.append({
                "trade_id": f"{stage}-{kind}-{symbol}-{entry.strftime('%Y%m%d')}-{formation_days}-{hold_days}-{top_targets}",
                "stage": stage, "kind": kind, "symbol": symbol, "category": SYMBOL_TO_CATEGORY[symbol],
                "decision_time": decision, "entry_time": entry, "exit_time": exit_time,
                "formation_days": formation_days, "hold_days": hold_days, "top_targets": top_targets,
                **diagnostics,
                "entry_price": entry_price, "exit_price": exit_price,
                "quantity_per_unit_plan_capital": quantity,
                "funding_events": int(len(rates)),
                "actual_funding_return": actual_funding,
                "stress_funding_return": stress_funding,
                "gross_price_return": float(CONFIG["notional_fraction"]) * (exit_price / entry_price - 1.0),
            })
            next_entry_after = exit_time + pd.Timedelta(days=1)
    return pd.DataFrame(rows), excluded_missing_funding


def vectorbt_long_returns(trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    if trades.empty:
        return np.array([], dtype=float)
    columns = trades["trade_id"].tolist()
    prices = pd.DataFrame(
        [trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)],
        index=pd.Index([0, 1], name="step"), columns=columns,
    )
    quantity = trades["quantity_per_unit_plan_capital"].to_numpy(float)
    sizes = pd.DataFrame([quantity, -quantity], index=prices.index, columns=columns)
    portfolio = vbt.Portfolio.from_orders(
        prices, size=sizes, size_type="amount", direction="both", fees=fee, slippage=slippage,
        init_cash=1.0, freq="1D",
    )
    return portfolio.total_return().reindex(columns).to_numpy(float)


def manual_long_return(row: pd.Series, fee: float, slippage: float) -> float:
    quantity = float(row["quantity_per_unit_plan_capital"])
    entry_execution = float(row["entry_price"]) * (1.0 + slippage)
    exit_execution = float(row["exit_price"]) * (1.0 - slippage)
    return quantity * (exit_execution - entry_execution) - quantity * entry_execution * fee - quantity * exit_execution * fee


def attach_returns(trades: pd.DataFrame) -> pd.DataFrame:
    output = trades.copy()
    if output.empty:
        return output
    for scenario, assumptions in CONFIG["costs"].items():
        vectorbt_return = vectorbt_long_returns(output, float(assumptions["fee_per_side"]), float(assumptions["slippage_per_side"]))
        manual = output.apply(
            manual_long_return, axis=1,
            fee=float(assumptions["fee_per_side"]), slippage=float(assumptions["slippage_per_side"]),
        ).to_numpy(float)
        funding_column = "stress_funding_return" if assumptions["funding_stress"] else "actual_funding_return"
        output[f"{scenario}_price_cost_return"] = vectorbt_return
        output[f"{scenario}_reconciliation_error"] = vectorbt_return - manual
        output[f"{scenario}_net_return"] = vectorbt_return + output[funding_column].to_numpy(float)
        hurdle = (1.0 + float(CONFIG["annual_capital_hurdle"])) ** (output["hold_days"].to_numpy(float) / 365.0) - 1.0
        output[f"{scenario}_after_hurdle_return"] = (1.0 + output[f"{scenario}_net_return"].to_numpy(float)) / (1.0 + hurdle) - 1.0
    return output


def circular_block_bootstrap(values: np.ndarray, block: int = 4, reps: int = 5000, seed: int = 20260722) -> list[float]:
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return [math.nan, math.nan]
    rng = np.random.default_rng(seed)
    means = np.empty(reps, dtype=float)
    effective_block = min(block, len(values))
    for index in range(reps):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(effective_block)) % len(values)).tolist())
        means[index] = values[np.asarray(chosen[: len(values)])].mean()
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def target_drawdown(group: pd.DataFrame, column: str) -> float:
    equity = (1.0 + group.sort_values("entry_time")[column].to_numpy(float)).cumprod()
    equity = np.r_[1.0, equity]
    running = np.maximum.accumulate(equity)
    return float(np.min(equity / running - 1.0))


def summarize(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {"trades": 0, "targets": 0, "categories": 0, "scenarios": {}}
    result: dict[str, Any] = {
        "trades": int(len(trades)), "entry_dates": int(trades["entry_time"].nunique()),
        "targets": int(trades["symbol"].nunique()), "categories": int(trades["category"].nunique()),
        "funding_events": int(trades["funding_events"].sum()),
        "selection_counts": {str(k): int(v) for k, v in trades["symbol"].value_counts().sort_index().items()},
        "category_counts": {str(k): int(v) for k, v in trades["category"].value_counts().sort_index().items()},
        "maximum_vectorbt_reconciliation_error": float(max(
            trades[f"{scenario}_reconciliation_error"].abs().max() for scenario in CONFIG["costs"]
        )),
        "scenarios": {}, "by_year_base_after_hurdle": {}, "by_target_base_after_hurdle": {},
        "by_category_base_after_hurdle": {},
    }
    for scenario in CONFIG["costs"]:
        column = f"{scenario}_after_hurdle_return"
        cohort = trades.groupby("entry_time")[column].mean().sort_index()
        result["scenarios"][scenario] = {
            "trade_mean_net_return": float(trades[f"{scenario}_net_return"].mean()),
            "trade_mean_after_hurdle": float(trades[column].mean()),
            "cohort_mean_after_hurdle": float(cohort.mean()),
            "cohort_bootstrap_95pct": circular_block_bootstrap(cohort.to_numpy(float)),
            "trade_win_rate_after_hurdle": float((trades[column] > 0).mean()),
            "trade_median_after_hurdle": float(trades[column].median()),
            "trade_5pct_after_hurdle": float(trades[column].quantile(0.05)),
        }
    base_column = "base_after_hurdle_return"
    for year, group in trades.groupby(trades["entry_time"].dt.year):
        result["by_year_base_after_hurdle"][str(year)] = float(group.groupby("entry_time")[base_column].mean().mean())
    target_stats: dict[str, Any] = {}
    for symbol, group in trades.groupby("symbol"):
        target_stats[symbol] = {
            "trades": int(len(group)), "mean": float(group[base_column].mean()),
            "sum": float(group[base_column].sum()), "max_drawdown": target_drawdown(group, base_column),
        }
    result["by_target_base_after_hurdle"] = target_stats
    eligible_targets = [value for value in target_stats.values() if value["trades"] >= 5]
    result["positive_target_fraction"] = float(np.mean([value["mean"] > 0 for value in eligible_targets])) if eligible_targets else 0.0
    drawdowns = [value["max_drawdown"] for value in eligible_targets]
    result["target_max_drawdown_median"] = float(np.median(drawdowns)) if drawdowns else -1.0
    result["target_max_drawdown_worst"] = float(np.min(drawdowns)) if drawdowns else -1.0
    for category, group in trades.groupby("category"):
        result["by_category_base_after_hurdle"][category] = {
            "trades": int(len(group)), "mean": float(group.groupby("entry_time")[base_column].mean().mean()),
        }
    result["positive_category_count"] = int(sum(
        value["trades"] >= 10 and value["mean"] > 0 for value in result["by_category_base_after_hurdle"].values()
    ))
    positive_sums = {symbol: max(0.0, value["sum"]) for symbol, value in target_stats.items()}
    denominator = sum(positive_sums.values())
    result["largest_positive_target_pnl_share"] = float(max(positive_sums.values()) / denominator) if denominator > 0 else 1.0
    result["gross_price_trade_mean"] = float(trades["gross_price_return"].mean())
    result["actual_funding_trade_mean"] = float(trades["actual_funding_return"].mean())
    return result


def diagnostic_spec(name: str) -> dict[str, Any]:
    return CONFIG["diagnostics"][name]


def command_analyze(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    stage_authorized(args.stage)
    quality_path = HERE / f"data_quality_{args.stage}.json"
    if not quality_path.exists() or read_json(quality_path)["status"] != "PASS":
        raise RuntimeError("stage data quality is not PASS")
    bars, funding = load_all(args.stage)
    main_raw, main_excluded = build_trades(
        args.stage, bars, funding, "max", int(CONFIG["formation_days"]),
        int(CONFIG["hold_days"]), int(CONFIG["top_targets"]),
    )
    main = attach_returns(main_raw)
    main.to_csv(HERE / f"{args.stage}_trades.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    main_summary = summarize(main)
    main_summary["excluded_trades_due_missing_funding_mark"] = main_excluded
    main_summary["excluded_trade_fraction"] = float(main_excluded / (len(main) + main_excluded)) if len(main) + main_excluded else 0.0
    diagnostic_results: dict[str, Any] = {}
    diagnostic_hashes: dict[str, str] = {}
    for name, spec in CONFIG["diagnostics"].items():
        diagnostic_raw, diagnostic_excluded = build_trades(
            args.stage, bars, funding, str(spec["kind"]), int(spec["formation_days"]),
            int(spec["hold_days"]), int(spec.get("top_targets", CONFIG["top_targets"])),
        )
        trades = attach_returns(diagnostic_raw)
        path = HERE / f"{args.stage}_{name}_trades.csv"
        trades.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
        diagnostic_results[name] = summarize(trades)
        diagnostic_results[name]["excluded_trades_due_missing_funding_mark"] = diagnostic_excluded
        diagnostic_results[name]["excluded_trade_fraction"] = float(
            diagnostic_excluded / (len(trades) + diagnostic_excluded)
        ) if len(trades) + diagnostic_excluded else 0.0
        diagnostic_hashes[name] = sha256_file(path)
    payload = {
        "generated_at_utc": iso_now(), "stage": args.stage,
        "period": {"start": STAGES[args.stage]["start"], "end_exclusive": STAGES[args.stage]["end_exclusive"]},
        "main": main_summary, "diagnostics": diagnostic_results,
        "search_disclosure": {"selectable_primary_configurations": 1, "parameter_neighborhoods_not_selectable": 3, "simple_baselines_not_selectable": 3},
        "trade_csv_sha256": sha256_file(HERE / f"{args.stage}_trades.csv"),
        "diagnostic_csv_sha256": diagnostic_hashes,
        "data_quality_digest": read_json(quality_path)["content_digest"],
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / f"{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage, "trades": payload["main"]["trades"],
        "base_after_hurdle": payload["main"]["scenarios"].get("base", {}).get("cohort_mean_after_hurdle"),
        "stress_after_hurdle": payload["main"]["scenarios"].get("stress", {}).get("cohort_mean_after_hurdle"),
    }))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    main = result["main"]
    scenarios = main.get("scenarios", {})
    base = scenarios.get("base", {})
    stress = scenarios.get("stress", {})
    minimum_trades, minimum_targets, minimum_entry_dates = {
        "development": (150, 20, 40),
        "evaluation": (75, 15, 20),
        "confirmation": (100, 15, 30),
    }[stage]
    expected_years = {
        "development": ["2022", "2023"], "evaluation": ["2024"], "confirmation": ["2025", "2026"],
    }[stage]
    neighbors = ["max21", "max35", "top5"]
    checks = {
        "data_quality_pass": read_json(HERE / f"data_quality_{stage}.json")["status"] == "PASS",
        "excluded_trade_fraction_at_most_limit": main.get("excluded_trade_fraction", 1.0) <= float(CONFIG["max_excluded_trade_fraction"]),
        "vectorbt_reconciled": main.get("maximum_vectorbt_reconciliation_error", 1.0) <= 1e-10,
        "trades_at_least_minimum": main.get("trades", 0) >= minimum_trades,
        "targets_at_least_minimum": main.get("targets", 0) >= minimum_targets,
        "entry_dates_at_least_minimum": main.get("entry_dates", 0) >= minimum_entry_dates,
        "categories_at_least_four": main.get("categories", 0) >= 4,
        "base_after_hurdle_positive": base.get("cohort_mean_after_hurdle", -1.0) > 0,
        "stress_after_hurdle_positive": stress.get("cohort_mean_after_hurdle", -1.0) > 0,
        "stress_bootstrap_lower_positive": (stress.get("cohort_bootstrap_95pct") or [-1.0])[0] > 0,
        "required_year_slices_positive": all(main.get("by_year_base_after_hurdle", {}).get(year, -1.0) > 0 for year in expected_years),
        "positive_target_fraction_at_least_half": main.get("positive_target_fraction", 0.0) >= 0.5,
        "positive_categories_at_least_four": main.get("positive_category_count", 0) >= 4,
        "beats_mom28": base.get("cohort_mean_after_hurdle", -1.0) > result["diagnostics"]["mom28"].get("scenarios", {}).get("base", {}).get("cohort_mean_after_hurdle", 1.0),
        "beats_last1": base.get("cohort_mean_after_hurdle", -1.0) > result["diagnostics"]["last1"].get("scenarios", {}).get("base", {}).get("cohort_mean_after_hurdle", 1.0),
        "beats_scheduled_long": base.get("cohort_mean_after_hurdle", -1.0) > result["diagnostics"]["scheduled_long"].get("scenarios", {}).get("base", {}).get("cohort_mean_after_hurdle", 1.0),
        "two_of_three_neighborhoods_stress_positive": sum(
            result["diagnostics"][name].get("scenarios", {}).get("stress", {}).get("cohort_mean_after_hurdle", -1.0) > 0
            for name in neighbors
        ) >= 2,
        "largest_positive_target_share_at_most_20pct": main.get("largest_positive_target_pnl_share", 1.0) <= 0.20,
        "median_target_drawdown_above_minus_20pct": main.get("target_max_drawdown_median", -1.0) > -0.20,
        "worst_target_drawdown_above_minus_40pct": main.get("target_max_drawdown_worst", -1.0) > -0.40,
    }
    return checks


def conclusion_for_failed_gate(result: dict[str, Any]) -> str:
    main = result["main"]
    scenarios = main.get("scenarios", {})
    minimum_trades, minimum_targets = {
        "development": (150, 20), "evaluation": (75, 15), "confirmation": (100, 15),
    }[result["stage"]]
    sample_ok = main.get("trades", 0) >= minimum_trades and main.get("targets", 0) >= minimum_targets
    economic_positive = all(scenarios.get(name, {}).get("cohort_mean_after_hurdle", -1.0) > 0 for name in ["base", "stress"])
    return "INSUFFICIENT_EVIDENCE" if sample_ok and economic_positive else "DOES_NOT_SUPPORT"


def command_gate(args: argparse.Namespace) -> None:
    result = read_json(HERE / f"{args.stage}.json")
    checks = gate_checks(args.stage, result)
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "generated_at_utc": iso_now(), "stage": args.stage, "status": status,
        "checks": checks, "failed_checks": [key for key, value in checks.items() if not value],
        "result_digest": result["content_digest"],
    }
    payload["content_digest"] = canonical_digest(payload)
    write_json(HERE / f"{args.stage}_gate.json", payload)
    if status == "FAIL":
        stopped = {
            "generated_at_utc": iso_now(), "conclusion": conclusion_for_failed_gate(result),
            "stopped_after": args.stage, "gate_status": status, "failed_checks": payload["failed_checks"],
            "main": result["main"], "diagnostics": result["diagnostics"],
            "later_stages": "NOT_OPENED_BY_SEQUENTIAL_GATE", "handoff": "NOT_GENERATED",
            "product_effects": "NONE",
        }
        stopped["content_digest"] = canonical_digest(stopped)
        write_json(HERE / "results.json", stopped)
    print(json.dumps({"stage": args.stage, "status": status, "failed": payload["failed_checks"]}))


def command_conclude(_args: argparse.Namespace) -> None:
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in STAGES}
    if not all(gate["status"] == "PASS" for gate in gates.values()):
        raise RuntimeError("cannot conclude support unless all sequential gates PASS")
    stages = {stage: read_json(HERE / f"{stage}.json") for stage in STAGES}
    combined_later_mean = float(np.mean([
        stages[stage]["main"]["scenarios"]["base"]["cohort_mean_after_hurdle"]
        for stage in ["evaluation", "confirmation"]
    ]))
    if combined_later_mean <= 0:
        raise RuntimeError("evaluation and confirmation combined mean is not positive")
    handoff = {
        "candidate_id": CONFIG["strategy_id"], "version": "1",
        "allowed_direction": "LONG", "notional_fraction_of_plan_capital": CONFIG["notional_fraction"],
        "inputs": ["daily OHLCV including quote volume for the fixed target universe", "UTC bar close/open timestamps"],
        "warmup_days": 30,
        "decision": (
            "After each completed UTC Sunday, require at least 20 targets with 30d median quote volume >=10m "
            "and complete MAX28. Rank eligible targets by their maximum close-to-close daily return over the prior "
            "28 complete days, descending with symbol as deterministic tie-break. Propose LONG for ranks one to three."
        ),
        "entry": "next Monday UTC daily open after the Sunday decision",
        "exit": "UTC daily open exactly seven days after entry; require one full UTC day before reactivation",
        "unknown_no_action": "missing, stale, discontinuous, invalid, insufficient targets, or incomplete ranking input",
        "costs": CONFIG["costs"], "unsupported_execution_facts": ["historical book depth", "queue and partial fills", "margin/liquidation/ADL", "user reactivation latency"],
        "framework_neutral_trace": [
            {"case": "rank_three", "target_volume_ok": True, "rankable_targets": 23, "max28": 0.18, "feature_rank": 3, "proposal": "LONG_ENTRY_NEXT_MONDAY_OPEN"},
            {"case": "rank_four", "target_volume_ok": True, "rankable_targets": 23, "max28": 0.17, "feature_rank": 4, "proposal": "NO_ACTION"},
            {"case": "insufficient_universe", "target_volume_ok": True, "rankable_targets": 19, "max28": 0.18, "feature_rank": None, "proposal": "NO_ACTION"},
        ],
        "research_result_digest": {stage: stages[stage]["content_digest"] for stage in STAGES},
        "limitations": "Current-survivor fixed target list, not a point-in-time full market; daily bars cannot model intraday path or book liquidity; research result does not authorize product or trading use.",
    }
    handoff["content_digest"] = canonical_digest(handoff)
    write_json(HERE / "handoff.json", handoff)
    result = {
        "generated_at_utc": iso_now(), "conclusion": "SUPPORTS_WITHIN_SCOPE",
        "stage_gates": {stage: gate["status"] for stage, gate in gates.items()},
        "stages": {stage: value["main"] for stage, value in stages.items()},
        "evaluation_confirmation_mean": combined_later_mean,
        "handoff_sha256": sha256_file(HERE / "handoff.json"), "product_effects": "NONE",
    }
    result["content_digest"] = canonical_digest(result)
    write_json(HERE / "results.json", result)
    print(json.dumps({"conclusion": result["conclusion"], "handoff": str(HERE / "handoff.json")}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Past-month MAX weekly one-shot LONG study")
    subparsers = parser.add_subparsers(dest="command", required=True)
    checkpoint = subparsers.add_parser("checkpoint")
    checkpoint.set_defaults(func=command_checkpoint)
    for command, function in [("fetch", command_fetch), ("inspect", command_inspect), ("analyze", command_analyze), ("gate", command_gate)]:
        item = subparsers.add_parser(command)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=function)
    conclude = subparsers.add_parser("conclude")
    conclude.set_defaults(func=command_conclude)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
