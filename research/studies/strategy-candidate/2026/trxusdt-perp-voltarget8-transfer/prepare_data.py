"""Prepare immutable full-history TRXUSDT USD-M inputs."""

from __future__ import annotations

import argparse
import csv
import io
import importlib.util
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType


STUDY_DIR = Path(__file__).resolve().parent
TRANSFER_PREPARE_PATH = (
    STUDY_DIR.parent / "trx-paxg-usdm-venue-transfer" / "prepare_data.py"
)
SYMBOL = "TRXUSDT"
FUNDING_ARCHIVE_BASE = (
    f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{SYMBOL}"
)
DAILY_GAP_FILL_DATES = (
    "2022-02-26",
    "2022-02-27",
    "2022-02-28",
    "2022-04-01",
    "2022-04-02",
)
MARK_GAP_FILL_DATES = (
    "2021-07-01",
    "2021-07-24",
    "2021-07-25",
    "2021-07-26",
    "2021-07-27",
    "2022-10-02",
    "2023-02-24",
)
UNAVAILABLE_MARK_GAP_DATE = "2026-06-29"


def _load_transfer_prepare() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "halpha_trx_full_prepare_base", TRANSFER_PREPARE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("TRANSFER_PREPARE_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PREPARE = _load_transfer_prepare()


def prepare(args: argparse.Namespace) -> None:
    root = Path(args.cache_root).resolve()
    symbol_root = root / SYMBOL.lower()
    months = PREPARE.BASE._month_range(args.start_month, args.end_month)
    start_ms = int(
        datetime.fromisoformat(args.funding_start.replace("Z", "+00:00")).timestamp()
        * 1000
    )
    end_ms = int(
        datetime.fromisoformat(args.funding_end.replace("Z", "+00:00")).timestamp()
        * 1000
    )
    exchange_info = PREPARE.BASE._get_json(PREPARE.EXCHANGE_INFO_URL)
    records = {
        item["symbol"]: item
        for item in exchange_info.get("symbols", [])
        if item.get("symbol") == SYMBOL
    }
    if SYMBOL not in records:
        raise ValueError("EXCHANGE_INFO_SYMBOL_MISSING")
    record = records[SYMBOL]
    if record.get("status") != "TRADING" or record.get("contractType") != "PERPETUAL":
        raise ValueError("CONTRACT_NOT_TRADING_PERPETUAL")
    archives = PREPARE.BASE._prepare_archives(
        cache_root=symbol_root,
        relative_root="klines-1d",
        base_url=(
            f"https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/1d"
        ),
        name_template=f"{SYMBOL}-1d-{{month}}.zip",
        months=months,
    )
    daily_gap_archives = PREPARE.BASE._prepare_archives(
        cache_root=symbol_root,
        relative_root="klines-1d-daily-gap-fill",
        base_url=(
            f"https://data.binance.vision/data/futures/um/daily/klines/{SYMBOL}/1d"
        ),
        name_template=f"{SYMBOL}-1d-{{month}}.zip",
        months=list(DAILY_GAP_FILL_DATES),
    )
    archives.extend(daily_gap_archives)
    mark_archives = PREPARE.BASE._prepare_archives(
        cache_root=symbol_root,
        relative_root="mark-price-klines-8h",
        base_url=(
            "https://data.binance.vision/data/futures/um/monthly/"
            f"markPriceKlines/{SYMBOL}/8h"
        ),
        name_template=f"{SYMBOL}-8h-{{month}}.zip",
        months=months,
    )
    daily_gap_mark_archives = PREPARE.BASE._prepare_archives(
        cache_root=symbol_root,
        relative_root="mark-price-klines-8h-daily-gap-fill",
        base_url=(
            "https://data.binance.vision/data/futures/um/daily/"
            f"markPriceKlines/{SYMBOL}/8h"
        ),
        name_template=f"{SYMBOL}-8h-{{month}}.zip",
        months=list(MARK_GAP_FILL_DATES),
    )
    mark_archives.extend(daily_gap_mark_archives)
    funding_archives = PREPARE.BASE._prepare_archives(
        cache_root=symbol_root,
        relative_root="funding-rate",
        base_url=FUNDING_ARCHIVE_BASE,
        name_template=f"{SYMBOL}-fundingRate-{{month}}.zip",
        months=months,
    )
    funding: list[dict[str, object]] = []
    for item in funding_archives:
        archive_path = symbol_root / item["cache_relative_path"]
        with zipfile.ZipFile(archive_path) as bundle:
            names = bundle.namelist()
            if len(names) != 1:
                raise ValueError("FUNDING_ARCHIVE_MEMBER_COUNT_INVALID")
            with bundle.open(names[0]) as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))
                for row in reader:
                    timestamp = int(row["calc_time"])
                    if start_ms <= timestamp < end_ms:
                        funding.append(
                            {
                                "symbol": SYMBOL,
                                "fundingTime": timestamp,
                                "fundingRate": str(row["last_funding_rate"]),
                                "markPrice": "",
                            }
                        )
    funding.sort(key=lambda item: int(item["fundingTime"]))
    timestamps = [int(item["fundingTime"]) for item in funding]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("FUNDING_DUPLICATE_TIMESTAMP")
    funding_path = symbol_root / "funding-rate-history.json"
    funding_path.write_text(
        json.dumps(funding, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    exchange_path = symbol_root / "exchange-info-record.json"
    exchange_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "venue": "Binance USD-M",
        "instrument": f"{SYMBOL} perpetual",
        "interval": "1d",
        "gap_fill_policy": {
            "kind": "official_daily_archives_only_for_timestamps_absent_from_checksum_verified_monthly_archives",
            "daily_kline_dates": list(DAILY_GAP_FILL_DATES),
            "mark_price_dates": list(MARK_GAP_FILL_DATES),
            "unavailable_mark_price_date_using_daily_open_fallback": UNAVAILABLE_MARK_GAP_DATE,
        },
        "archives": archives,
        "mark_price_archives": mark_archives,
        "funding_archives": funding_archives,
        "funding_snapshot": {
            "url": FUNDING_ARCHIVE_BASE,
            "requested_start": args.funding_start,
            "requested_end_exclusive": args.funding_end,
            "cache_relative_path": funding_path.relative_to(symbol_root).as_posix(),
            "sha256": PREPARE.BASE._sha256(funding_path),
            "records": len(funding),
            "first_funding_time": funding[0]["fundingTime"] if funding else None,
            "last_funding_time": funding[-1]["fundingTime"] if funding else None,
        },
        "exchange_info_snapshot": {
            "url": PREPARE.EXCHANGE_INFO_URL,
            "cache_relative_path": exchange_path.relative_to(symbol_root).as_posix(),
            "sha256": PREPARE.BASE._sha256(exchange_path),
            "status": record["status"],
            "contractType": record["contractType"],
            "onboardDate": record["onboardDate"],
        },
    }
    manifest_path = symbol_root / "source_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output = {
        "symbol": SYMBOL,
        "cache_root": symbol_root.as_posix(),
        "manifest": manifest_path.as_posix(),
        "manifest_sha256": PREPARE.BASE._sha256(manifest_path),
        "archives": len(archives),
        "mark_price_archives": len(mark_archives),
        "funding_archives": len(funding_archives),
        "funding_records": len(funding),
    }
    print(json.dumps(output, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--start-month", default="2020-01")
    parser.add_argument("--end-month", default="2026-06")
    parser.add_argument("--funding-start", default="2020-01-01T00:00:00Z")
    parser.add_argument("--funding-end", default="2026-07-01T00:00:00Z")
    args = parser.parse_args()
    prepare(args)


if __name__ == "__main__":
    main()
