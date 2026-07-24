"""Reproducible BTC relationship research and a standalone local monitor.

Public market-data reads only. This module never imports product code, reads product
configuration, or exposes an exchange-changing operation.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
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
RESEARCH_ROOT = next(
    (path for path in QUESTION_DIR.parents if path.name == "research"), None
)
if RESEARCH_ROOT is None:
    raise RuntimeError(f"cannot locate research root from {QUESTION_DIR}")
if str(RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(RESEARCH_ROOT))

from halpha_research_data import data_root  # noqa: E402 - research-root local helper


UNIVERSE_PATH = RESEARCH_ROOT / "market-universe" / "universe.csv"
EVIDENCE_DIR = QUESTION_DIR / "evidence"
APP_DIR = QUESTION_DIR / "app"
DEFAULT_CACHE_ROOT = data_root() / "btc-market-relationship-monitor"
EXTERNAL_SERVICE_REGISTRY_ENV = "HALPHA_EXTERNAL_SERVICE_REGISTRY"
EXTERNAL_SERVICE_REGISTRY_SCHEMA = 1
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


def external_service_registry_directory() -> Path:
    override = os.environ.get(EXTERNAL_SERVICE_REGISTRY_ENV)
    if override:
        return Path(override).expanduser().resolve()
    local_data = os.environ.get("LOCALAPPDATA")
    if local_data:
        return Path(local_data) / "Halpha" / "external-services"
    return Path.home() / ".local" / "share" / "Halpha" / "external-services"


def register_external_service(service_id: str, pid: int, listener: str) -> Path:
    directory = external_service_registry_directory()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{service_id}.json"
    temporary = directory / f".{service_id}.{pid}.tmp"
    temporary.write_text(
        json.dumps(
            {
                "schema_version": EXTERNAL_SERVICE_REGISTRY_SCHEMA,
                "service_id": service_id,
                "pid": pid,
                "listeners": [listener],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return target


def unregister_external_service(path: Path, pid: int) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return
    if payload.get("pid") == pid:
        path.unlink(missing_ok=True)


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


def sha256_gzip_payload(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_input_identity(
    cutoff: datetime,
    universe_identity: dict[str, Any],
    fetch_results: dict[str, "FetchResult"],
    coin_metrics: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    binance = {}
    for symbol, result in sorted(fetch_results.items()):
        cache_path = Path(result.cache_path)
        binance[symbol] = {
            "rows": result.rows,
            "latest_close_time_utc": result.latest_close_time_utc,
            "cache_content_sha256": (
                sha256_gzip_payload(cache_path)
                if result.rows and cache_path.is_file()
                else None
            ),
        }
    coin_metrics_path = Path(coin_metrics.get("cache_path", ""))
    payload = {
        "cutoff_utc": iso_z(cutoff),
        "universe_sha256": universe_identity["sha256"],
        "binance": binance,
        "coin_metrics_cache_content_sha256": (
            sha256_gzip_payload(coin_metrics_path)
            if coin_metrics_path.is_file()
            else None
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), payload


def _temporary_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_sibling(path)
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _cache_relative_path(cache_root: Path, path: str | Path) -> str:
    return Path(path).resolve().relative_to(cache_root.resolve()).as_posix()


def _data_key(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(data_root()).as_posix()
    except ValueError:
        return None


@contextmanager
def _exclusive_refresh_lock(cache_root: Path):
    lock_path = cache_root / "current" / ".refresh.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(f"another refresh already owns {lock_path}") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _retained_manifest_path(cache_root: Path, input_identity_sha256: str) -> Path:
    return (
        cache_root
        / "snapshots"
        / "by-input"
        / input_identity_sha256
        / "source-manifest.json"
    )


def _load_retained_source(
    cache_root: Path, input_identity_sha256: str
) -> dict[str, Any] | None:
    manifest_path = _retained_manifest_path(cache_root, input_identity_sha256)
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshot_dir = manifest_path.parent.resolve()
        expected_parent = (cache_root / "snapshots" / "by-input").resolve()
        if snapshot_dir.parent != expected_parent:
            return None
        if manifest["schema_version"] != 2:
            return None
        if manifest["input_identity_sha256"] != input_identity_sha256:
            return None
        encoded_identity = json.dumps(
            manifest["input_identity"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if hashlib.sha256(encoded_identity).hexdigest() != input_identity_sha256:
            return None
        verified_inputs: dict[tuple[str, str | None], Path] = {}
        for item in manifest["normalized_inputs"]:
            candidate = (snapshot_dir / item["relative_path"]).resolve()
            if not candidate.is_relative_to(snapshot_dir) or not candidate.is_file():
                return None
            if candidate.stat().st_size != item["bytes"]:
                return None
            if sha256_file(candidate) != item["sha256"]:
                return None
            verified_inputs[(item["kind"], item.get("symbol"))] = candidate
        for symbol, item in manifest["input_identity"]["binance"].items():
            expected = item["cache_content_sha256"]
            if expected is None:
                continue
            candidate = verified_inputs.get(("binance-spot-1d", symbol))
            if candidate is None or sha256_gzip_payload(candidate) != expected:
                return None
        expected_coin_metrics = manifest["input_identity"][
            "coin_metrics_cache_content_sha256"
        ]
        if expected_coin_metrics is not None:
            candidate = verified_inputs.get(("coin-metrics-price-usd", None))
            if (
                candidate is None
                or sha256_gzip_payload(candidate) != expected_coin_metrics
            ):
                return None
        expected_universe = manifest["input_identity"]["universe_sha256"]
        if manifest["universe"]["sha256"] != expected_universe:
            return None
        universe = verified_inputs.get(("market-universe", None))
        if universe is None or sha256_file(universe) != expected_universe:
            return None
        return {
            "schema_version": 2,
            "input_identity_sha256": input_identity_sha256,
            "source_manifest_relative_path": _cache_relative_path(
                cache_root, manifest_path
            ),
            "source_manifest_data_key": _data_key(manifest_path),
            "source_manifest_sha256": sha256_file(manifest_path),
            "retained_at_utc": manifest["retained_at_utc"],
        }
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _select_retained_source(
    cache_root: Path,
    requested_identity: str | None = None,
) -> dict[str, Any] | None:
    if requested_identity is not None:
        if len(requested_identity) != 64 or any(
            character not in "0123456789abcdef" for character in requested_identity
        ):
            raise ValueError(
                "input identity must be 64 lowercase hexadecimal characters"
            )
        retained = _load_retained_source(cache_root, requested_identity)
        if retained is None:
            raise RuntimeError(
                f"verified retained source is unavailable for {requested_identity}"
            )
        return retained

    pointer_path = cache_root / "current" / "retained-source.json"
    if pointer_path.is_file():
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            identity = pointer["input_identity_sha256"]
            retained = _load_retained_source(cache_root, identity)
            if retained is not None:
                return retained
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            pass

    candidates: list[tuple[str, str]] = []
    by_input = cache_root / "snapshots" / "by-input"
    if by_input.is_dir():
        for manifest_path in by_input.glob("*/source-manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                candidates.append(
                    (
                        str(manifest["retained_at_utc"]),
                        str(manifest["input_identity_sha256"]),
                    )
                )
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
    for _, identity in sorted(candidates, reverse=True):
        retained = _load_retained_source(cache_root, identity)
        if retained is not None:
            return retained
    return None


def _write_retained_source(cache_root: Path, pointer: dict[str, Any]) -> None:
    pointer_path = cache_root / "current" / "retained-source.json"
    _atomic_write_text(pointer_path, json.dumps(pointer, indent=2) + "\n")


def _link_or_copy(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def _fetch_result_value(cache_root: Path, result: "FetchResult") -> dict[str, Any]:
    value = {key: item for key, item in result.__dict__.items() if key != "cache_path"}
    value["cache_relative_path"] = _cache_relative_path(cache_root, result.cache_path)
    return value


def _fetch_observation(
    cache_root: Path,
    fetch_results: dict[str, "FetchResult"],
    coin_metrics: dict[str, Any],
) -> dict[str, Any]:
    binance = []
    for symbol, result in sorted(fetch_results.items()):
        binance.append(_fetch_result_value(cache_root, result))
    coin_metrics_value = {
        key: value for key, value in coin_metrics.items() if key != "cache_path"
    }
    cache_path = coin_metrics.get("cache_path")
    if cache_path:
        coin_metrics_value["cache_relative_path"] = _cache_relative_path(
            cache_root, cache_path
        )
    return {"binance": binance, "coin_metrics": coin_metrics_value}


def _retain_normalized_source(
    cache_root: Path,
    cutoff: datetime,
    input_identity_sha256: str,
    input_identity: dict[str, Any],
    universe_identity: dict[str, Any],
    fetch_results: dict[str, "FetchResult"],
    coin_metrics: dict[str, Any],
) -> dict[str, Any]:
    existing = _load_retained_source(cache_root, input_identity_sha256)
    if existing is not None:
        return existing

    final_dir = _retained_manifest_path(cache_root, input_identity_sha256).parent
    parent = final_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = parent / (
        f".{input_identity_sha256}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    normalized_inputs: list[dict[str, Any]] = []
    try:
        for symbol, result in sorted(fetch_results.items()):
            source = Path(result.cache_path)
            if result.rows == 0 or not source.is_file():
                continue
            relative_path = Path("inputs") / "binance-spot-1d" / f"{symbol}.csv.gz"
            target = temporary / relative_path
            materialization = _link_or_copy(source, target)
            normalized_inputs.append(
                {
                    "kind": "binance-spot-1d",
                    "symbol": symbol,
                    "relative_path": relative_path.as_posix(),
                    "bytes": target.stat().st_size,
                    "sha256": sha256_file(target),
                    "materialization": materialization,
                }
            )

        coin_metrics_path = Path(coin_metrics.get("cache_path", ""))
        if coin_metrics_path.is_file():
            relative_path = Path("inputs") / "coin-metrics-price-usd.csv.gz"
            target = temporary / relative_path
            materialization = _link_or_copy(coin_metrics_path, target)
            normalized_inputs.append(
                {
                    "kind": "coin-metrics-price-usd",
                    "relative_path": relative_path.as_posix(),
                    "bytes": target.stat().st_size,
                    "sha256": sha256_file(target),
                    "materialization": materialization,
                }
            )

        universe_relative = Path("inputs") / "market-universe.csv"
        universe_target = temporary / universe_relative
        universe_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(UNIVERSE_PATH, universe_target)
        normalized_inputs.append(
            {
                "kind": "market-universe",
                "relative_path": universe_relative.as_posix(),
                "bytes": universe_target.stat().st_size,
                "sha256": sha256_file(universe_target),
                "materialization": "copy",
            }
        )

        if not normalized_inputs:
            raise RuntimeError("no normalized inputs were available for retention")
        manifest = {
            "schema_version": 2,
            "input_identity_sha256": input_identity_sha256,
            "input_identity": input_identity,
            "cutoff_utc": iso_z(cutoff),
            "retained_at_utc": iso_z(utc_now()),
            "universe": universe_identity,
            "normalized_inputs": normalized_inputs,
            "source_observation": {
                "offline": False,
                "binance_endpoint": BINANCE_URL,
                "coin_metrics_endpoint": COIN_METRICS_URL,
                "coin_metrics_metric": COIN_METRICS_FIELD,
                **_fetch_observation(cache_root, fetch_results, coin_metrics),
            },
            "replay_note": (
                "The immutable normalized_inputs are the complete analytical inputs for this "
                "cutoff; source_observation records acquisition status and is not a substitute "
                "for those bytes."
            ),
        }
        (temporary / "source-manifest.json").write_text(
            json.dumps(_json_safe(manifest), indent=2) + "\n", encoding="utf-8"
        )
        if final_dir.exists():
            shutil.rmtree(temporary)
        else:
            os.replace(temporary, final_dir)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise

    retained = _load_retained_source(cache_root, input_identity_sha256)
    if retained is None:
        raise RuntimeError("retained normalized input snapshot failed verification")
    return retained


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
        active["economic_exposure_source"].eq(
            "DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS"
        )
        & active["classification_subtypes"].eq("")
        & active["base_asset"].str.endswith("B")
        & ~active["base_asset"].isin(KNOWN_CRYPTO_SUFFIX_B_EXCEPTIONS)
    )
    excluded_bstocks = active[bstock_mask].sort_values("symbol")
    active = active[~bstock_mask].copy()
    active = active.drop_duplicates(subset=["symbol"], keep="last").sort_values(
        "symbol"
    )
    if REFERENCE_SYMBOL not in set(active["symbol"]):
        raise ValueError(
            f"reference {REFERENCE_SYMBOL} is absent from the recorded universe"
        )
    snapshot_values = sorted(set(active["snapshot_time_utc"]))
    if len(snapshot_values) != 1:
        raise ValueError(f"universe has non-unique snapshot times: {snapshot_values}")
    try:
        relative_path = path.resolve().relative_to(RESEARCH_ROOT.resolve()).as_posix()
    except ValueError:
        relative_path = path.name
    identity = {
        "research_relative_path": relative_path,
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
    temporary = _temporary_sibling(path)
    try:
        frame.to_csv(
            temporary,
            index=False,
            compression="gzip",
            float_format="%.12g",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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


@dataclass(frozen=True)
class RetainedReplaySource:
    identity_sha256: str
    cutoff: datetime
    universe_path: Path
    fetch_results: dict[str, FetchResult]
    coin_metrics: dict[str, Any]


def _retained_replay_source(
    cache_root: Path,
    requested_identity: str | None = None,
) -> RetainedReplaySource | None:
    retained = _select_retained_source(cache_root, requested_identity)
    if retained is None:
        return None
    identity = retained["input_identity_sha256"]
    manifest_path = _retained_manifest_path(cache_root, identity)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_dir = manifest_path.parent
    inputs = {
        (item["kind"], item.get("symbol")): snapshot_dir / item["relative_path"]
        for item in manifest["normalized_inputs"]
    }
    observed_binance = {
        item["symbol"]: item for item in manifest["source_observation"]["binance"]
    }
    fetch_results: dict[str, FetchResult] = {}
    for symbol, identity_value in manifest["input_identity"]["binance"].items():
        observation = observed_binance.get(symbol, {})
        expected_content = identity_value["cache_content_sha256"]
        cache_path = inputs.get(("binance-spot-1d", symbol))
        if expected_content is None:
            fetch_results[symbol] = FetchResult(
                symbol=symbol,
                status=str(observation.get("status", "MISSING_RETAINED")),
                cache_path="",
                rows=0,
                latest_close_time_utc=None,
                error=observation.get("error"),
                quality=observation.get("quality"),
            )
            continue
        if cache_path is None:
            raise RuntimeError(
                f"retained source is missing normalized input for {symbol}"
            )
        fetch_results[symbol] = FetchResult(
            symbol=symbol,
            status="RETAINED_SNAPSHOT",
            cache_path=str(cache_path),
            rows=int(identity_value["rows"]),
            latest_close_time_utc=identity_value["latest_close_time_utc"],
            raw_sha256=observation.get("raw_sha256"),
            cache_sha256=sha256_file(cache_path),
            error=observation.get("error"),
            quality=observation.get("quality"),
        )

    coin_metrics = dict(manifest["source_observation"]["coin_metrics"])
    coin_metrics_path = inputs.get(("coin-metrics-price-usd", None))
    expected_coin_metrics = manifest["input_identity"][
        "coin_metrics_cache_content_sha256"
    ]
    if expected_coin_metrics is None:
        coin_metrics["cache_path"] = ""
    elif coin_metrics_path is None:
        raise RuntimeError("retained source is missing the Coin Metrics input")
    else:
        coin_metrics["cache_path"] = str(coin_metrics_path)
        coin_metrics["cache_sha256"] = sha256_file(coin_metrics_path)
        coin_metrics["status"] = "RETAINED_SNAPSHOT"

    cutoff = datetime.fromisoformat(
        str(manifest["cutoff_utc"]).replace("Z", "+00:00")
    ).astimezone(UTC)
    universe_path = inputs.get(("market-universe", None))
    if universe_path is None:
        raise RuntimeError("retained source is missing the market universe input")
    return RetainedReplaySource(
        identity_sha256=identity,
        cutoff=cutoff,
        universe_path=universe_path,
        fetch_results=fetch_results,
        coin_metrics=coin_metrics,
    )


def fetch_symbol(
    symbol: str,
    cache_root: Path,
    cutoff: datetime,
    offline: bool,
    timeout_seconds: float = 20,
) -> FetchResult:
    cache_path = cache_root / "current" / "binance-spot-1d" / f"{symbol}.csv.gz"
    current = _read_cache(cache_path)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    if offline:
        if current.empty:
            return FetchResult(
                symbol,
                "MISSING_OFFLINE",
                str(cache_path),
                0,
                None,
                error="cache missing",
            )
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
        if current.empty:
            combined = normalized
        else:
            combined = pd.concat([current, normalized], ignore_index=True)
            combined = combined.drop_duplicates(subset=["open_time_ms"], keep="last")
            combined = combined[
                pd.to_numeric(combined["close_time_ms"], errors="coerce") <= cutoff_ms
            ]
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
    except (
        Exception
    ) as exc:  # network failures are surfaced and last-good cache is retained
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
    cutoff: datetime,
    offline: bool,
) -> dict[str, Any]:
    cache_path = cache_root / "current" / "coin-metrics-price-usd.csv.gz"
    if offline:
        return {
            "status": "CACHE_ONLY" if cache_path.exists() else "MISSING_OFFLINE",
            "cache_path": str(cache_path),
        }
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
            response = get_with_retry(
                COIN_METRICS_URL, params=params, timeout=30, attempts=2
            )
            raw = response.content
            payload = response.json()
            records = payload.get("data", [])
            frame = pd.DataFrame(records)
            if frame.empty or COIN_METRICS_FIELD not in frame:
                raise ValueError(f"no Coin Metrics {COIN_METRICS_FIELD} data returned")
            frame[COIN_METRICS_FIELD] = pd.to_numeric(
                frame[COIN_METRICS_FIELD], errors="coerce"
            )
            frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
            frame = frame.dropna(subset=["asset", "time", COIN_METRICS_FIELD])
            frame = frame[frame[COIN_METRICS_FIELD] > 0].sort_values(["asset", "time"])
            frames.append(frame[["asset", "time", COIN_METRICS_FIELD]])
            asset_status[asset] = {
                "status": "FETCHED",
                "rows": len(frame),
                "raw_sha256": sha256_bytes(raw),
            }
        except Exception as exc:
            asset_status[asset] = {
                "status": "UNAVAILABLE",
                "error": f"{type(exc).__name__}: {exc}",
            }
    if frames:
        combined = pd.concat(frames, ignore_index=True).sort_values(["asset", "time"])
        _write_cache(combined, cache_path)
        return {
            "status": "FETCHED_WITH_GAPS"
            if any(item["status"] != "FETCHED" for item in asset_status.values())
            else "FETCHED",
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


def crosscheck_coin_metrics(
    cache_path: str | Path, binance_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not cache_path:
        return []
    path = Path(cache_path)
    if not path.is_file():
        return []
    frame = pd.read_csv(path)
    if frame.empty:
        return []
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame[COIN_METRICS_FIELD] = pd.to_numeric(
        frame[COIN_METRICS_FIELD], errors="coerce"
    )
    prices = {
        asset: group.set_index("time")[COIN_METRICS_FIELD].dropna().sort_index()
        for asset, group in frame.groupby("asset")
    }
    if "btc" not in prices:
        return []
    by_symbol = {
        row["symbol"]: row for row in binance_results if row.get("status") == "ANALYZED"
    }
    checks: list[dict[str, Any]] = []
    for symbol, asset in ANCHOR_CROSSCHECK.items():
        if symbol == REFERENCE_SYMBOL:
            continue
        if asset not in prices:
            checks.append(
                {"symbol": symbol, "status": "UNAVAILABLE_FROM_COIN_METRICS_COMMUNITY"}
            )
            continue
        if symbol not in by_symbol:
            checks.append({"symbol": symbol, "status": "PRIMARY_NOT_ANALYZED"})
            continue
        cm_result, _ = analyze_pair(symbol, prices[asset], prices["btc"])
        if cm_result.get("status") != "ANALYZED":
            checks.append(
                {
                    "symbol": symbol,
                    "status": cm_result.get("status"),
                    "n_obs": cm_result.get("n_obs"),
                }
            )
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
                "direction_agreement": bool(
                    np.sign(primary["pearson"]) == np.sign(cm_result["pearson"])
                ),
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
    rolling_cache: dict[str, list[dict[str, Any]]],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    refresh_id = str(manifest["refresh_id"])
    generations_root = output_dir / "generations"
    generations_root.mkdir(parents=True, exist_ok=True)
    generation_dir = generations_root / refresh_id
    temporary = generations_root / (
        f".{refresh_id}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    if generation_dir.exists():
        raise FileExistsError(generation_dir)
    temporary.mkdir()
    frame = pd.DataFrame(results).sort_values(
        ["statistically_significant", "strong_association", "pearson", "symbol"],
        ascending=[False, False, False, True],
        na_position="last",
    )
    csv_outputs = {
        "results.csv": frame,
        "significant-associations.csv": frame[
            frame["statistically_significant"] == True  # noqa: E712
        ],
        "strong-associations.csv": frame[
            frame["strong_association"] == True  # noqa: E712
        ],
        "not-analyzed.csv": frame[frame["status"] != "ANALYZED"],
    }
    try:
        for name, output in csv_outputs.items():
            output.to_csv(
                temporary / name,
                index=False,
                float_format="%.10g",
                quoting=csv.QUOTE_MINIMAL,
            )
        (temporary / "summary.json").write_text(
            json.dumps(_json_safe(summary), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        generation_relative_path = (Path("generations") / refresh_id).as_posix()
        manifest = {
            **manifest,
            "output_generation_relative_path": generation_relative_path,
        }
        (temporary / "data-manifest.json").write_text(
            json.dumps(_json_safe(manifest), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with gzip.open(
            temporary / "rolling-90d.json.gz",
            "wt",
            encoding="utf-8",
        ) as handle:
            json.dump(rolling_cache, handle, separators=(",", ":"))
        os.replace(temporary, generation_dir)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise

    manifest_path = generation_dir / "data-manifest.json"
    pointer = {
        "schema_version": 1,
        "refresh_id": refresh_id,
        "generation_relative_path": (Path("generations") / refresh_id).as_posix(),
        "manifest_sha256": sha256_file(manifest_path),
    }
    _atomic_write_text(
        output_dir / "current-generation.json",
        json.dumps(pointer, indent=2) + "\n",
    )
    previous = sorted(
        (
            candidate
            for candidate in generations_root.iterdir()
            if candidate.is_dir()
            and not candidate.name.startswith(".")
            and candidate != generation_dir
        ),
        key=lambda candidate: candidate.stat().st_mtime_ns,
        reverse=True,
    )
    for obsolete in previous[1:]:
        try:
            shutil.rmtree(obsolete)
        except OSError:
            pass
    return generation_dir


def _generation_dir(output_dir: Path, refresh_id: str) -> Path | None:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{12}Z", refresh_id) is None:
        return None
    try:
        expected_relative = (Path("generations") / refresh_id).as_posix()
        generation = (output_dir / expected_relative).resolve()
        generations_root = (output_dir / "generations").resolve()
        if generation.parent != generations_root or not generation.is_dir():
            return None
        manifest_path = generation / "data-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["refresh_id"] != refresh_id:
            return None
        required = {
            "results.csv",
            "significant-associations.csv",
            "strong-associations.csv",
            "not-analyzed.csv",
            "summary.json",
            "data-manifest.json",
            "rolling-90d.json.gz",
        }
        if any(not (generation / name).is_file() for name in required):
            return None
        return generation
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _current_generation_dir(output_dir: Path) -> Path | None:
    pointer_path = output_dir / "current-generation.json"
    if not pointer_path.is_file():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if pointer["schema_version"] != 1:
            return None
        refresh_id = str(pointer["refresh_id"])
        expected_relative = (Path("generations") / refresh_id).as_posix()
        if pointer["generation_relative_path"] != expected_relative:
            return None
        generation = _generation_dir(output_dir, refresh_id)
        if generation is None:
            return None
        if (
            sha256_file(generation / "data-manifest.json")
            != pointer["manifest_sha256"]
        ):
            return None
        return generation
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _refresh_unlocked(
    cache_root: Path = DEFAULT_CACHE_ROOT,
    offline: bool = False,
    workers: int = 8,
    output_dir: Path | None = None,
    input_identity_sha256: str | None = None,
) -> dict[str, Any]:
    started = utc_now()
    refresh_id = started.strftime("%Y-%m-%dT%H%M%S%fZ")
    replay_source = (
        _retained_replay_source(cache_root, input_identity_sha256) if offline else None
    )
    if replay_source is not None:
        cutoff = replay_source.cutoff
        universe, universe_identity = load_universe(replay_source.universe_path)
        fetch_results = replay_source.fetch_results
        coin_metrics = replay_source.coin_metrics
    else:
        cutoff = latest_closed_cutoff(started)
        universe, universe_identity = load_universe()
        symbols_to_fetch = universe["symbol"].tolist()
        fetch_results = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
            futures = {
                pool.submit(
                    fetch_symbol,
                    symbol,
                    cache_root,
                    cutoff,
                    offline,
                ): symbol
                for symbol in symbols_to_fetch
            }
            for future in as_completed(futures):
                result = future.result()
                fetch_results[result.symbol] = result
        coin_metrics = fetch_coin_metrics(cache_root, cutoff, offline)
    symbols = universe["symbol"].tolist()
    missing_fetch_results = [
        symbol for symbol in symbols if symbol not in fetch_results
    ]
    for symbol in missing_fetch_results:
        fetch_results[symbol] = FetchResult(
            symbol=symbol,
            status="MISSING_RETAINED",
            cache_path="",
            rows=0,
            latest_close_time_utc=None,
            error="symbol was not present in the selected retained input identity",
        )
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
            row, rolling = analyze_pair(
                symbol, _price_series(fetched.cache_path), btc_price
            )
        row.update(
            {
                "base_asset": metadata[symbol]["base_asset"],
                "economic_exposure": metadata[symbol]["economic_exposure"],
                "economic_exposure_source": metadata[symbol][
                    "economic_exposure_source"
                ],
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
                {"time": index.isoformat(), "pearson": float(value)}
                for index, value in rolling.items()
            ]
    apply_multiple_testing(results)
    crosschecks = crosscheck_coin_metrics(coin_metrics.get("cache_path", ""), results)
    analyzed = [row for row in results if row["status"] == "ANALYZED"]
    significant = [row for row in analyzed if row["statistically_significant"]]
    strong = [row for row in analyzed if row["strong_association"]]
    failed = [
        result
        for result in fetch_results.values()
        if result.status in {"FAILED", "MISSING_OFFLINE"}
    ]
    stale = [
        result
        for result in fetch_results.values()
        if result.status == "STALE_CACHE_AFTER_ERROR"
    ]
    status = "OK"
    if (
        failed
        or stale
        or coin_metrics.get("status")
        in {"FAILED", "STALE_CACHE_AFTER_ERROR", "MISSING_OFFLINE"}
    ):
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
            "insufficient_sample": sum(
                row["status"] == "INSUFFICIENT_SAMPLE" for row in results
            ),
            "fetch_failed": len(failed),
            "stale_cache": len(stale),
            "statistically_significant": len(significant),
            "strong_association": len(strong),
        },
        "median_beta": float(np.median([row["beta"] for row in analyzed]))
        if analyzed
        else None,
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
        "failures": [
            _fetch_result_value(cache_root, result)
            for result in sorted(failed + stale, key=lambda item: item.symbol)
        ],
        "top_strong": sorted(strong, key=lambda row: abs(row["pearson"]), reverse=True)[
            :20
        ],
        "warnings": [
            "Current-list survivorship: the universe is not reconstructed point-in-time.",
            "Association is not causation, lead-lag, prediction, strategy evidence, or Alpha.",
            "Daily single-venue closes do not identify intraday spillovers or execution quality.",
        ],
    }
    input_identity_sha256, input_identity = _stable_input_identity(
        cutoff, universe_identity, fetch_results, coin_metrics
    )
    if (
        replay_source is not None
        and input_identity_sha256 != replay_source.identity_sha256
    ):
        raise RuntimeError(
            "retained source no longer reproduces its recorded input identity "
            f"(expected {replay_source.identity_sha256}, got {input_identity_sha256})"
        )
    retained = _load_retained_source(cache_root, input_identity_sha256)
    source_manifest_reused = retained is not None
    retention_warning = None
    if retained is None and not offline:
        retained = _retain_normalized_source(
            cache_root,
            cutoff,
            input_identity_sha256,
            input_identity,
            universe_identity,
            fetch_results,
            coin_metrics,
        )
    elif retained is None:
        retention_warning = (
            "Offline refresh used mutable current caches because no verified immutable snapshot "
            "exists for this input identity; offline runs never promote current caches to evidence."
        )
        summary["warnings"].append(retention_warning)
    if retained is not None:
        _write_retained_source(cache_root, retained)
    manifest = {
        "schema_version": 2,
        "refresh_id": refresh_id,
        "offline": offline,
        "cache_namespace": cache_root.name,
        "data_root_env": "HALPHA_RESEARCH_DATA_ROOT",
        "cache_root_argument_required": bool(
            retained is not None and retained["source_manifest_data_key"] is None
        ),
        "input_identity_sha256": input_identity_sha256,
        "source_retained": retained is not None,
        "source_manifest_reused": source_manifest_reused,
        "source_manifest_relative_path": (
            retained["source_manifest_relative_path"] if retained else None
        ),
        "source_manifest_data_key": (
            retained["source_manifest_data_key"] if retained else None
        ),
        "source_manifest_sha256": (
            retained["source_manifest_sha256"] if retained else None
        ),
        "retention_warning": retention_warning,
        "universe": universe_identity,
        "cutoff_utc": iso_z(cutoff),
        "result_rows": len(results),
        "result_identity_note": (
            "When source_retained is true, source_manifest identifies complete immutable "
            "normalized analytical inputs. Offline refreshes may read mutable current caches "
            "but never promote them to retained evidence."
        ),
    }
    _write_outputs(
        results,
        summary,
        manifest,
        rolling_cache,
        output_dir or cache_root / "live",
    )
    return summary


def refresh(
    cache_root: Path = DEFAULT_CACHE_ROOT,
    offline: bool = False,
    workers: int = 8,
    output_dir: Path | None = None,
    input_identity_sha256: str | None = None,
) -> dict[str, Any]:
    if input_identity_sha256 is not None and not offline:
        raise ValueError("an input identity may be selected only for an offline replay")
    with _exclusive_refresh_lock(cache_root):
        return _refresh_unlocked(
            cache_root,
            offline,
            workers,
            output_dir,
            input_identity_sha256,
        )


class MonitorState:
    def __init__(
        self, cache_root: Path, output_dir: Path, refresh_seconds: int, workers: int
    ) -> None:
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
            refresh(
                self.cache_root,
                offline=False,
                workers=self.workers,
                output_dir=self.output_dir,
            )
            self.last_error = None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            self.next_attempt = iso_z(
                utc_now() + timedelta(seconds=self.refresh_seconds)
            )
            self.lock.release()

    def result_path(self, name: str) -> Path:
        generation = _current_generation_dir(self.output_dir)
        if generation is not None:
            generated_path = generation / name
            if generated_path.is_file():
                return generated_path
        live_path = self.output_dir / name
        return live_path if live_path.exists() else EVIDENCE_DIR / name

    def pinned_result_path(self, name: str, refresh_id: str) -> Path | None:
        if refresh_id == "evidence":
            return EVIDENCE_DIR / name
        if refresh_id == "flat-live":
            return self.output_dir / name
        generation = _generation_dir(self.output_dir, refresh_id)
        if generation is None:
            return None
        path = generation / name
        return path if path.is_file() else None

    def generation_id_for_path(self, path: Path) -> str | None:
        resolved = path.resolve()
        if resolved.parent == EVIDENCE_DIR.resolve():
            return "evidence"
        if resolved.parent == self.output_dir.resolve():
            return "flat-live"
        try:
            relative = resolved.relative_to(
                (self.output_dir / "generations").resolve()
            )
        except ValueError:
            return None
        if len(relative.parts) != 2:
            return None
        refresh_id = relative.parts[0]
        return (
            refresh_id
            if _generation_dir(self.output_dir, refresh_id) is not None
            else None
        )


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def make_handler(state: MonitorState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "HalphaResearchMonitor/1.0"

        def _send(
            self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            # Plotly applies calculated layout through element.style. Scripts
            # remain self-hosted; only inline CSS is permitted.
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(
                json.dumps(
                    _json_safe(payload), ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/favicon.ico":
                self._send(b"", "image/x-icon", HTTPStatus.NO_CONTENT)
                return
            if parsed.path == "/":
                self._send(
                    (APP_DIR / "index.html").read_bytes(), "text/html; charset=utf-8"
                )
                return
            if parsed.path == "/app.js":
                self._send(
                    (APP_DIR / "app.js").read_bytes(),
                    "application/javascript; charset=utf-8",
                )
                return
            if parsed.path == "/styles.css":
                self._send(
                    (APP_DIR / "styles.css").read_bytes(), "text/css; charset=utf-8"
                )
                return
            if parsed.path == "/plotly.min.js":
                self._send(
                    plotly.offline.get_plotlyjs().encode("utf-8"),
                    "application/javascript; charset=utf-8",
                )
                return
            if parsed.path == "/api/summary":
                path = state.result_path("summary.json")
                if not path.exists():
                    self._json(
                        {"status": "NOT_READY", "last_error": state.last_error},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return
                payload = _load_json(path)
                payload["generation_id"] = state.generation_id_for_path(path)
                payload["monitor"] = {
                    "refresh_in_progress": state.lock.locked(),
                    "last_attempt_utc": state.last_attempt,
                    "next_attempt_utc": state.next_attempt,
                    "last_error": state.last_error,
                }
                self._json(payload)
                return
            if parsed.path == "/api/results":
                generation_id = query.get("generation", [None])[0]
                path = (
                    state.pinned_result_path("results.csv", generation_id)
                    if generation_id
                    else state.result_path("results.csv")
                )
                if path is None:
                    self._json(
                        {"error": "generation unavailable; reload summary"},
                        HTTPStatus.CONFLICT,
                    )
                    return
                if not path.exists():
                    self._json(
                        {"error": "results not ready"}, HTTPStatus.SERVICE_UNAVAILABLE
                    )
                    return
                frame = pd.read_csv(path)
                self._json(frame.replace({np.nan: None}).to_dict(orient="records"))
                return
            if parsed.path == "/api/detail":
                symbol = query.get("symbol", [""])[0].upper()
                if not symbol.isalnum() or len(symbol) > 30:
                    self._json({"error": "invalid symbol"}, HTTPStatus.BAD_REQUEST)
                    return
                generation_id = query.get("generation", [None])[0]
                rolling_path = (
                    state.pinned_result_path("rolling-90d.json.gz", generation_id)
                    if generation_id
                    else state.result_path("rolling-90d.json.gz")
                )
                if rolling_path is None:
                    self._json(
                        {"error": "generation unavailable; reload summary"},
                        HTTPStatus.CONFLICT,
                    )
                    return
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
    bound_host, bound_port = server.server_address[:2]
    pid = os.getpid()
    registration_path: Path | None = None
    try:
        registration_path = register_external_service(
            f"btc-market-relationship-monitor-{bound_port}",
            pid,
            f"{bound_host}:{bound_port}",
        )
        if not no_initial_refresh:
            threading.Thread(target=state.run_refresh, daemon=True).start()

        def background() -> None:
            while True:
                state.next_attempt = iso_z(utc_now() + timedelta(seconds=refresh_seconds))
                time.sleep(refresh_seconds)
                state.run_refresh()

        threading.Thread(target=background, daemon=True).start()
        print(f"BTC relationship monitor: http://{bound_host}:{bound_port}")
        print("Metrics use closed daily bars; polling does not create intraday metric changes.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    finally:
        try:
            server.server_close()
        finally:
            if registration_path is not None:
                unregister_external_service(registration_path, pid)


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
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Replay a verified retained source, or use current caches when none exists.",
    )
    parser.add_argument(
        "--input-identity",
        default=None,
        help="Exact retained input SHA-256 to replay with --offline.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--refresh-seconds", type=int, default=900)
    parser.add_argument("--no-initial-refresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "refresh":
        summary = refresh(
            args.cache_root,
            args.offline,
            args.workers,
            args.output_dir,
            args.input_identity,
        )
        print(json.dumps(_json_safe(summary["counts"]), ensure_ascii=False, indent=2))
        print(f"status={summary['status']} cutoff={summary['data_cutoff_utc']}")
        return 0 if summary["status"] in {"OK", "PARTIAL"} else 2
    if args.offline:
        raise SystemExit("--offline applies only to refresh")
    if args.input_identity is not None:
        raise SystemExit("--input-identity applies only to an offline refresh")
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
