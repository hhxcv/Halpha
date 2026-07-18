"""Rebuild the exact B04 ParquetDataCatalog from verified Binance archives."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any
import zipfile

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider


DATASET_ID = "b04-btcusdt-1m-2022-01_2026-06"
RAW_ROOT = ROOT / "build" / "evidence" / "raw" / DATASET_ID
CATALOG_ROOT = ROOT / "build" / "evidence" / "catalog" / DATASET_ID
PREREGISTRATION_PATH = ROOT / "build" / "evidence" / "reports" / "b04-historical-preregistration.json"
DATA_EVIDENCE_PATH = ROOT / "build" / "qualification" / "b04-historical-data.json"
CATALOG_EVIDENCE_PATH = ROOT / "build" / "qualification" / "b04-historical-catalog.json"
BAR_TYPE = BarType.from_str("BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL")
COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_base",
    "taker_quote",
    "ignore",
)


class HistoricalCatalogError(RuntimeError):
    """Sanitized B04 historical catalog failure."""


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


def _load_verified(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    recorded = payload.pop("evidence_digest", None)
    if recorded != _digest(payload):
        raise HistoricalCatalogError("UPSTREAM_EVIDENCE_DIGEST_MISMATCH")
    payload["evidence_digest"] = recorded
    return payload


def _instrument(rules: dict[str, Any]) -> CryptoPerpetual:
    template = TestInstrumentProvider.btcusdt_perp_binance()
    return CryptoPerpetual(
        instrument_id=template.id,
        raw_symbol=template.raw_symbol,
        base_currency=template.base_currency,
        quote_currency=template.quote_currency,
        settlement_currency=template.settlement_currency,
        is_inverse=template.is_inverse,
        price_precision=int(rules["price_precision"]),
        size_precision=int(rules["quantity_precision"]),
        price_increment=Price.from_str(rules["price_tick_size"]),
        size_increment=Quantity.from_str(rules["market_step_size"]),
        ts_event=template.ts_event,
        ts_init=template.ts_init,
        multiplier=template.multiplier,
        lot_size=template.lot_size,
        max_quantity=Quantity.from_str(rules["market_max_quantity"]),
        min_quantity=Quantity.from_str(rules["market_min_quantity"]),
        min_notional=Money.from_str(f"{rules['min_notional']} USDT"),
        max_price=template.max_price,
        min_price=template.min_price,
        margin_init=template.margin_init,
        margin_maint=template.margin_maint,
        maker_fee=Decimal("0.0006"),
        taker_fee=Decimal("0.0006"),
    )


def _read_month(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        member = archive.namelist()[0]
        with archive.open(member) as raw:
            first_line = raw.readline()
            raw.seek(0)
            has_header = first_line.startswith(b"open_time")
            frame = pd.read_csv(
                raw,
                names=COLUMNS,
                header=0 if has_header else None,
                usecols=("open_time", "open", "high", "low", "close", "volume"),
                dtype={
                    "open_time": "int64",
                    "open": "float64",
                    "high": "float64",
                    "low": "float64",
                    "close": "float64",
                    "volume": "float64",
                },
            )
    frame.index = pd.to_datetime(frame["open_time"] + 60_000, unit="ms", utc=True)
    return frame[["open", "high", "low", "close", "volume"]]


def _inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _file_digest(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def main() -> int:
    CATALOG_EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine: ParquetDataCatalog | None = None
    try:
        preregistration = _load_verified(PREREGISTRATION_PATH)
        data_evidence = _load_verified(DATA_EVIDENCE_PATH)
        if data_evidence["status"] != "QUALIFIED":
            raise HistoricalCatalogError("HISTORICAL_DATA_NOT_QUALIFIED")
        if (
            data_evidence["preregistration_digest"]
            != preregistration["evidence_digest"]
        ):
            raise HistoricalCatalogError("PREREGISTRATION_BINDING_MISMATCH")
        if CATALOG_ROOT.exists():
            shutil.rmtree(CATALOG_ROOT)
        CATALOG_ROOT.mkdir(parents=True)
        instrument = _instrument(preregistration["instrument_rules"])
        engine = ParquetDataCatalog(CATALOG_ROOT)
        engine.write_data([instrument])
        wrangler = BarDataWrangler(BAR_TYPE, instrument)
        month_results: list[dict[str, Any]] = []
        total_bars = 0
        for archive in preregistration["data"]["archives"]:
            archive_path = RAW_ROOT / archive["filename"]
            if _file_digest(archive_path) != archive["actual_sha256"]:
                raise HistoricalCatalogError("RAW_ARCHIVE_DIGEST_DRIFT")
            frame = _read_month(archive_path)
            bars = wrangler.process(frame)
            if len(bars) != archive["expected_rows"]:
                raise HistoricalCatalogError("WRANGLER_MONTH_ROW_COUNT_MISMATCH")
            engine.write_data(bars)
            month_results.append(
                {
                    "filename": archive["filename"],
                    "input_rows": len(frame),
                    "output_bars": len(bars),
                    "first_ts_event_ns": bars[0].ts_event,
                    "last_ts_event_ns": bars[-1].ts_event,
                }
            )
            total_bars += len(bars)
        catalog_instruments = engine.instruments(instrument_ids=[str(instrument.id)])
        first = engine.query(
            Bar,
            identifiers=[str(BAR_TYPE)],
            start="2022-01-01T00:01:00Z",
            end="2022-01-01T00:02:00Z",
        )
        last = engine.query(
            Bar,
            identifiers=[str(BAR_TYPE)],
            start="2026-06-30T23:59:00Z",
            end="2026-07-01T00:00:00Z",
        )
        inventory = _inventory(CATALOG_ROOT)
        evidence: dict[str, Any] = {
            "schema_version": 1,
            "stage": "B04_HISTORICAL_PARQUET_CATALOG",
            "status": "QUALIFIED",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "dataset_id": DATASET_ID,
            "preregistration_digest": preregistration["evidence_digest"],
            "data_evidence_digest": data_evidence["evidence_digest"],
            "catalog_implementation": "nautilus_trader.persistence.catalog.ParquetDataCatalog",
            "wrangler_implementation": "nautilus_trader.persistence.wranglers.BarDataWrangler",
            "timestamp_mapping": "BINANCE_OPEN_TIME_PLUS_60000MS_TO_CLOSED_BAR_EVENT",
            "float_boundary": (
                "PANDAS_FLOAT64_ONLY_AT_PUBLIC_WRANGLER_INPUT; "
                "NAUTILUS_INSTRUMENT_PRECISION_OWNS_FIXED_POINT_BAR_VALUES"
            ),
            "instrument_count": len(catalog_instruments),
            "bar_count": total_bars,
            "expected_bar_count": (
                data_evidence["development"]["row_count"]
                + data_evidence["holdout"]["row_count"]
            ),
            "first_bar_query_count": len(first),
            "last_bar_query_count": len(last),
            "month_results": month_results,
            "catalog_inventory": inventory,
            "catalog_inventory_digest": _digest(inventory),
            "raw_archives_retained": True,
            "product_database_or_record_created": False,
            "errors": [],
        }
    except Exception as exc:
        evidence = {
            "schema_version": 1,
            "stage": "B04_HISTORICAL_PARQUET_CATALOG",
            "status": "REJECTED",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "dataset_id": DATASET_ID,
            "product_database_or_record_created": False,
            "errors": [f"HISTORICAL_CATALOG_FAILED:{type(exc).__name__}"],
        }
    evidence["evidence_digest"] = _digest(evidence)
    CATALOG_EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
