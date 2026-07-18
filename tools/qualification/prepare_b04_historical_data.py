"""Prepare the exact B04 Binance BTCUSDT 1m historical evidence input."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener
import zipfile


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from halpha.planning.registry import Direction, OneShotParameters


DATASET_ID = "b04-btcusdt-1m-2022-01_2026-06"
RAW_ROOT = ROOT / "build" / "evidence" / "raw" / DATASET_ID
REPORT_ROOT = ROOT / "build" / "evidence" / "reports"
PREREGISTRATION_PATH = REPORT_ROOT / "b04-historical-preregistration.json"
EVIDENCE_PATH = ROOT / "build" / "qualification" / "b04-historical-data.json"
BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m"
EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
SHA256_PATTERN = re.compile(r"^([0-9a-fA-F]{64})\s+\*?([^\s]+)\s*$")
SOURCE_FILES = (
    "src/halpha/planning/adapter.py",
    "src/halpha/planning/bar_evaluation.py",
    "src/halpha/planning/indicators.py",
    "src/halpha/planning/registry.py",
    "src/halpha/planning/strategies/one_shot.py",
    "requirements/runtime.txt",
)


class HistoricalDataError(RuntimeError):
    """Sanitized failure for the B04 historical input preparation boundary."""


@dataclass(frozen=True)
class ArchiveSpec:
    year: int
    month: int

    @property
    def stem(self) -> str:
        return f"BTCUSDT-1m-{self.year:04d}-{self.month:02d}.zip"

    @property
    def start_ms(self) -> int:
        return int(datetime(self.year, self.month, 1, tzinfo=UTC).timestamp() * 1000)

    @property
    def end_ms_exclusive(self) -> int:
        if self.month == 12:
            value = datetime(self.year + 1, 1, 1, tzinfo=UTC)
        else:
            value = datetime(self.year, self.month + 1, 1, tzinfo=UTC)
        return int(value.timestamp() * 1000)

    @property
    def expected_rows(self) -> int:
        return (self.end_ms_exclusive - self.start_ms) // 60_000


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _archive_specs() -> tuple[ArchiveSpec, ...]:
    values: list[ArchiveSpec] = []
    year, month = 2022, 1
    while (year, month) <= (2026, 6):
        values.append(ArchiveSpec(year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return tuple(values)


def _opener() -> tuple[Any, bool]:
    proxy = os.environ.get("HALPHA_RUNTIME_PROXY_URL")
    if proxy is None:
        return build_opener(ProxyHandler({})), False
    parsed = urlparse(proxy)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise HistoricalDataError("RUNTIME_PROXY_NOT_LOOPBACK_OR_CONTAINS_CREDENTIALS")
    return build_opener(ProxyHandler({"http": proxy, "https": proxy})), True


def _request_bytes(opener: Any, url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Halpha-B04-evidence/1"})
    try:
        with opener.open(request, timeout=30) as response:
            return response.read()
    except Exception as exc:
        raise HistoricalDataError(
            f"OFFICIAL_SOURCE_REQUEST_FAILED type={type(exc).__name__}"
        ) from None


def _download_file(opener: Any, url: str, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "Halpha-B04-evidence/1"})
    try:
        with opener.open(request, timeout=60) as response, temporary.open("wb") as output:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                output.write(block)
        temporary.replace(destination)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise HistoricalDataError(
            f"OFFICIAL_ARCHIVE_DOWNLOAD_FAILED type={type(exc).__name__}"
        ) from None


def _prepare_archive(spec: ArchiveSpec) -> dict[str, Any]:
    opener, _ = _opener()
    archive_path = RAW_ROOT / spec.stem
    checksum_path = RAW_ROOT / f"{spec.stem}.CHECKSUM"
    checksum_bytes = _request_bytes(opener, f"{BASE_URL}/{spec.stem}.CHECKSUM")
    checksum_text = checksum_bytes.decode("ascii").strip()
    match = SHA256_PATTERN.fullmatch(checksum_text)
    if match is None or Path(match.group(2)).name != spec.stem:
        raise HistoricalDataError("OFFICIAL_CHECKSUM_FORMAT_INVALID")
    official_digest = match.group(1).lower()
    if not checksum_path.exists() or checksum_path.read_bytes() != checksum_bytes:
        checksum_path.write_bytes(checksum_bytes)
    if not archive_path.exists() or _file_digest(archive_path) != official_digest:
        archive_path.unlink(missing_ok=True)
        _download_file(opener, f"{BASE_URL}/{spec.stem}", archive_path)
    actual_digest = _file_digest(archive_path)
    if actual_digest != official_digest:
        archive_path.unlink(missing_ok=True)
        raise HistoricalDataError("OFFICIAL_ARCHIVE_CHECKSUM_MISMATCH")
    return {
        "filename": spec.stem,
        "official_sha256": official_digest,
        "actual_sha256": actual_digest,
        "size_bytes": archive_path.stat().st_size,
        "start_ms": spec.start_ms,
        "end_ms_exclusive": spec.end_ms_exclusive,
        "expected_rows": spec.expected_rows,
    }


def _read_exchange_rules(opener: Any) -> dict[str, Any]:
    try:
        payload = json.loads(_request_bytes(opener, EXCHANGE_INFO_URL))
        symbol = next(item for item in payload["symbols"] if item["symbol"] == "BTCUSDT")
        filters = {item["filterType"]: item for item in symbol["filters"]}
        price = filters["PRICE_FILTER"]
        market_lot = filters["MARKET_LOT_SIZE"]
        min_notional = filters["MIN_NOTIONAL"]
        return {
            "source": "BINANCE_USDM_LIVE_PUBLIC_EXCHANGE_INFO",
            "symbol": "BTCUSDT",
            "price_precision": symbol["pricePrecision"],
            "quantity_precision": symbol["quantityPrecision"],
            "price_tick_size": price["tickSize"],
            "market_step_size": market_lot["stepSize"],
            "market_min_quantity": market_lot["minQty"],
            "market_max_quantity": market_lot["maxQty"],
            "min_notional": min_notional["notional"],
        }
    except HistoricalDataError:
        raise
    except Exception as exc:
        raise HistoricalDataError(
            f"EXCHANGE_RULE_SNAPSHOT_INVALID type={type(exc).__name__}"
        ) from None


def _source_digests() -> dict[str, str]:
    return {relative: _file_digest(ROOT / relative) for relative in SOURCE_FILES}


def _preregistration_payload(
    archives: list[dict[str, Any]],
    exchange_rules: dict[str, Any],
    *,
    proxy_supplied: bool,
) -> dict[str, Any]:
    parameters = OneShotParameters(
        direction=Direction.LONG,
        channel_lookback_15m=96,
        confirmation_bars_1m=3,
        initial_stop_atr_multiple="1.0",
        max_entry_extension_atr="0.1",
        take_profit_1_r="1.0",
        take_profit_1_fraction="0.75",
        take_profit_2_r="2.0",
        max_hold_bars_15m=96,
        entry_valid_minutes=1440,
    ).model_dump(mode="json")
    build_manifest = ROOT / "build" / "release" / "build-manifest.json"
    return {
        "schema_version": 1,
        "stage": "B04_HISTORICAL_PREREGISTRATION",
        "status": "FROZEN_BEFORE_HOLDOUT_READ",
        "owner_selection_basis": "OWNER_DELEGATED_CONSERVATIVE_DECISION",
        "strategy": {
            "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "strategy_version": "1.0.0",
            "parameters": parameters,
            "parameter_digest": _digest(parameters),
            "direction": "LONG",
        },
        "data": {
            "dataset_id": DATASET_ID,
            "source": "BINANCE_OFFICIAL_USDM_PUBLIC_MONTHLY_KLINES",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "development_period": "2022-01-01T00:00:00Z/2024-12-31T23:59:59.999Z",
            "holdout_period": "2025-01-01T00:00:00Z/2026-06-30T23:59:59.999Z",
            "archives": archives,
            "missing_samples_interpolated": False,
        },
        "instrument_rules": exchange_rules,
        "capital": {
            "max_margin": "100",
            "max_notional": "500",
            "max_allowed_loss": "50",
            "effective_leverage": "5",
            "effective_leverage_source": "BACKTEST_MANIFEST_LEVERAGE_PROXY",
        },
        "engine": {
            "implementation": "nautilus_trader.backtest.engine.BacktestEngine",
            "bar_type": "BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL",
            "target_bar_type": "BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL@1-MINUTE-EXTERNAL",
            "time_bars_interval_type": "left-open",
            "time_bars_timestamp_on_close": True,
            "time_bars_skip_first_non_full_bar": True,
            "time_bars_build_with_no_updates": False,
            "validate_data_sequence": True,
            "fee_model": "MakerTakerFeeModel",
            "maker_fee": "0.0006",
            "taker_fee": "0.0006",
            "slippage_model": "OneTickSlippageFillModel",
            "latency_nanos": {
                "base": 1_000_000,
                "insert": 2_000_000,
                "update": 3_000_000,
                "cancel": 4_000_000,
            },
            "funding_model": "NOT_MODELED",
            "bar_adaptive_high_low_ordering": True,
            "liquidity_consumption": False,
            "reporter": "ReportProvider",
        },
        "source_digests": _source_digests(),
        "build_manifest_sha256": (
            _file_digest(build_manifest) if build_manifest.is_file() else None
        ),
        "build_manifest_release_eligible": False,
        "source_state": "WORKTREE_UNCOMMITTED_INTERMEDIATE",
        "proxy_supplied": proxy_supplied,
        "proxy_value_persisted": False,
        "system_proxy_modified": False,
    }


def _freeze_preregistration(payload: dict[str, Any]) -> dict[str, Any]:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    expected_content_digest = _digest(payload)
    if PREREGISTRATION_PATH.exists():
        existing_full = json.loads(PREREGISTRATION_PATH.read_text(encoding="utf-8"))
        existing_without_digest = {
            key: value
            for key, value in existing_full.items()
            if key != "evidence_digest"
        }
        recorded_digest = existing_full.get("evidence_digest")
        existing_payload = {
            key: value
            for key, value in existing_without_digest.items()
            if key != "observed_at"
        }
        if (
            recorded_digest != _digest(existing_without_digest)
            or existing_payload != payload
        ):
            raise HistoricalDataError("PREREGISTRATION_DRIFT")
        return existing_full
    frozen = {
        **payload,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    frozen["evidence_digest"] = _digest(frozen)
    PREREGISTRATION_PATH.write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if expected_content_digest != _digest(payload):
        raise HistoricalDataError("PREREGISTRATION_WRITE_CONFLICT")
    return frozen


def _scan_archive(spec: ArchiveSpec) -> dict[str, Any]:
    archive_path = RAW_ROOT / spec.stem
    rows = 0
    gaps = 0
    duplicates_or_out_of_order = 0
    invalid_ohlcv = 0
    invalid_close_time = 0
    first_open_ms: int | None = None
    last_open_ms: int | None = None
    expected_open_ms = spec.start_ms
    with zipfile.ZipFile(archive_path) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise HistoricalDataError("ARCHIVE_CRC_INVALID")
        members = [item for item in archive.namelist() if not item.endswith("/")]
        expected_csv = spec.stem.removesuffix(".zip") + ".csv"
        if len(members) != 1 or Path(members[0]).name != expected_csv:
            raise HistoricalDataError("ARCHIVE_MEMBER_TOPOLOGY_INVALID")
        with archive.open(members[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            for row in reader:
                if row and row[0] == "open_time":
                    continue
                if len(row) != 12:
                    raise HistoricalDataError("KLINE_COLUMN_COUNT_INVALID")
                try:
                    open_ms = int(row[0])
                    close_ms = int(row[6])
                    open_price, high, low, close, volume = (
                        Decimal(row[1]),
                        Decimal(row[2]),
                        Decimal(row[3]),
                        Decimal(row[4]),
                        Decimal(row[5]),
                    )
                except (ValueError, InvalidOperation):
                    raise HistoricalDataError("KLINE_VALUE_INVALID") from None
                if first_open_ms is None:
                    first_open_ms = open_ms
                last_open_ms = open_ms
                if open_ms > expected_open_ms:
                    gaps += (open_ms - expected_open_ms) // 60_000
                    expected_open_ms = open_ms + 60_000
                elif open_ms < expected_open_ms:
                    duplicates_or_out_of_order += 1
                else:
                    expected_open_ms += 60_000
                if close_ms != open_ms + 59_999:
                    invalid_close_time += 1
                if (
                    min(open_price, high, low, close) <= 0
                    or volume < 0
                    or high < max(open_price, close)
                    or low > min(open_price, close)
                    or high < low
                ):
                    invalid_ohlcv += 1
                rows += 1
    if expected_open_ms < spec.end_ms_exclusive:
        gaps += (spec.end_ms_exclusive - expected_open_ms) // 60_000
    return {
        "filename": spec.stem,
        "row_count": rows,
        "expected_rows": spec.expected_rows,
        "first_open_ms": first_open_ms,
        "last_open_ms": last_open_ms,
        "gap_count": gaps,
        "duplicate_or_out_of_order_count": duplicates_or_out_of_order,
        "invalid_close_time_count": invalid_close_time,
        "invalid_ohlcv_count": invalid_ohlcv,
    }


def main() -> int:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    specs = _archive_specs()
    prepared: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_prepare_archive, spec): spec for spec in specs}
            for future in as_completed(futures):
                prepared.append(future.result())
        prepared.sort(key=lambda item: item["filename"])
        opener, proxy_supplied = _opener()
        exchange_rules = _read_exchange_rules(opener)
        preregistration = _freeze_preregistration(
            _preregistration_payload(
                prepared,
                exchange_rules,
                proxy_supplied=proxy_supplied,
            )
        )
        development = [_scan_archive(spec) for spec in specs if spec.year <= 2024]
        holdout = [_scan_archive(spec) for spec in specs if spec.year >= 2025]
        scans = [*development, *holdout]
        for scan in scans:
            if scan["row_count"] != scan["expected_rows"]:
                errors.append(f"ROW_COUNT_MISMATCH:{scan['filename']}")
            for field in (
                "gap_count",
                "duplicate_or_out_of_order_count",
                "invalid_close_time_count",
                "invalid_ohlcv_count",
            ):
                if scan[field] != 0:
                    errors.append(f"{field.upper()}:{scan['filename']}")
        evidence: dict[str, Any] = {
            "schema_version": 1,
            "stage": "B04_HISTORICAL_DATA_PREPARATION",
            "status": "QUALIFIED" if not errors else "REJECTED",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "dataset_id": DATASET_ID,
            "preregistration_ref": PREREGISTRATION_PATH.relative_to(ROOT).as_posix(),
            "preregistration_digest": preregistration["evidence_digest"],
            "preregistration_frozen_before_holdout_read": True,
            "archive_count": len(prepared),
            "development": {
                "archive_count": len(development),
                "row_count": sum(item["row_count"] for item in development),
                "scans": development,
            },
            "holdout": {
                "archive_count": len(holdout),
                "row_count": sum(item["row_count"] for item in holdout),
                "scans": holdout,
            },
            "data_quality": {
                "gap_count": sum(item["gap_count"] for item in scans),
                "duplicate_or_out_of_order_count": sum(
                    item["duplicate_or_out_of_order_count"] for item in scans
                ),
                "invalid_close_time_count": sum(
                    item["invalid_close_time_count"] for item in scans
                ),
                "invalid_ohlcv_count": sum(
                    item["invalid_ohlcv_count"] for item in scans
                ),
                "missing_samples_interpolated": False,
            },
            "proxy_supplied": proxy_supplied,
            "proxy_value_persisted": False,
            "system_proxy_modified": False,
            "errors": errors,
        }
    except Exception as exc:
        evidence = {
            "schema_version": 1,
            "stage": "B04_HISTORICAL_DATA_PREPARATION",
            "status": "REJECTED",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "dataset_id": DATASET_ID,
            "proxy_supplied": bool(os.environ.get("HALPHA_RUNTIME_PROXY_URL")),
            "proxy_value_persisted": False,
            "system_proxy_modified": False,
            "errors": [f"HISTORICAL_DATA_PREPARATION_FAILED:{type(exc).__name__}"],
        }
    evidence["evidence_digest"] = _digest(evidence)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
