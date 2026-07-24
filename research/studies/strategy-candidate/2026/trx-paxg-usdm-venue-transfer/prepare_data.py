"""Prepare immutable TRXUSDT and PAXGUSDT USD-M venue-transfer inputs."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any


STUDY_DIR = Path(__file__).resolve().parent
BASE_PREPARE_PATH = (
    STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "prepare_data.py"
)
SYMBOLS = ("TRXUSDT", "PAXGUSDT")
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "halpha_trx_paxg_prepare_base", BASE_PREPARE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_PREPARE_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base()


def _funding_history(symbol: str, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cursor = start_ms
    while cursor < end_ms:
        query = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": 1000,
            }
        )
        page = BASE._get_json(f"{FUNDING_URL}?{query}")
        if not isinstance(page, list):
            raise ValueError("FUNDING_RESPONSE_NOT_LIST")
        if not page:
            break
        for item in page:
            timestamp = int(item["fundingTime"])
            if start_ms <= timestamp < end_ms:
                records.append(
                    {
                        "symbol": str(item.get("symbol", symbol)),
                        "fundingTime": timestamp,
                        "fundingRate": str(item["fundingRate"]),
                        "markPrice": str(item.get("markPrice", "")),
                    }
                )
        next_cursor = int(page[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise ValueError("FUNDING_PAGINATION_STALLED")
        cursor = next_cursor
        if len(page) < 1000:
            break
    records.sort(key=lambda item: int(item["fundingTime"]))
    timestamps = [int(item["fundingTime"]) for item in records]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("FUNDING_DUPLICATE_TIMESTAMP")
    return records


def _prepare_symbol(
    root: Path,
    symbol: str,
    months: list[str],
    start_ms: int,
    end_ms: int,
    start_text: str,
    end_text: str,
    exchange_record: dict[str, Any],
) -> dict[str, Any]:
    symbol_root = root / symbol.lower()
    archives = BASE._prepare_archives(
        cache_root=symbol_root,
        relative_root="klines-1d",
        base_url=f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/1d",
        name_template=f"{symbol}-1d-{{month}}.zip",
        months=months,
    )
    mark_archives = BASE._prepare_archives(
        cache_root=symbol_root,
        relative_root="mark-price-klines-8h",
        base_url=f"https://data.binance.vision/data/futures/um/monthly/markPriceKlines/{symbol}/8h",
        name_template=f"{symbol}-8h-{{month}}.zip",
        months=months,
    )
    funding = _funding_history(symbol, start_ms, end_ms)
    funding_path = symbol_root / "funding-rate-history.json"
    funding_path.write_text(
        json.dumps(funding, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    exchange_path = symbol_root / "exchange-info-record.json"
    exchange_path.write_text(
        json.dumps(exchange_record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "venue": "Binance USD-M",
        "instrument": f"{symbol} perpetual",
        "interval": "1d",
        "archives": archives,
        "mark_price_archives": mark_archives,
        "funding_snapshot": {
            "url": FUNDING_URL,
            "requested_start": start_text,
            "requested_end_exclusive": end_text,
            "cache_relative_path": funding_path.relative_to(symbol_root).as_posix(),
            "sha256": BASE._sha256(funding_path),
            "records": len(funding),
            "first_funding_time": funding[0]["fundingTime"] if funding else None,
            "last_funding_time": funding[-1]["fundingTime"] if funding else None,
        },
        "exchange_info_snapshot": {
            "url": EXCHANGE_INFO_URL,
            "cache_relative_path": exchange_path.relative_to(symbol_root).as_posix(),
            "sha256": BASE._sha256(exchange_path),
            "status": exchange_record["status"],
            "contractType": exchange_record["contractType"],
            "onboardDate": exchange_record["onboardDate"],
        },
    }
    manifest_path = symbol_root / "source_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "symbol": symbol,
        "cache_root": symbol_root.as_posix(),
        "manifest": manifest_path.as_posix(),
        "manifest_sha256": BASE._sha256(manifest_path),
        "archives": len(archives),
        "mark_price_archives": len(mark_archives),
        "funding_records": len(funding),
    }


def prepare(args: argparse.Namespace) -> None:
    root = Path(args.cache_root).resolve()
    months = BASE._month_range(args.start_month, args.end_month)
    start_ms = int(
        datetime.fromisoformat(args.funding_start.replace("Z", "+00:00")).timestamp()
        * 1000
    )
    end_ms = int(
        datetime.fromisoformat(args.funding_end.replace("Z", "+00:00")).timestamp()
        * 1000
    )
    exchange_info = BASE._get_json(EXCHANGE_INFO_URL)
    records = {
        item["symbol"]: item
        for item in exchange_info.get("symbols", [])
        if item.get("symbol") in SYMBOLS
    }
    if set(records) != set(SYMBOLS):
        raise ValueError("EXCHANGE_INFO_SYMBOL_MISSING")
    for symbol, item in records.items():
        if item.get("status") != "TRADING" or item.get("contractType") != "PERPETUAL":
            raise ValueError(f"CONTRACT_NOT_TRADING_PERPETUAL:{symbol}")
    outputs = [
        _prepare_symbol(
            root,
            symbol,
            months,
            start_ms,
            end_ms,
            args.funding_start,
            args.funding_end,
            records[symbol],
        )
        for symbol in SYMBOLS
    ]
    print(json.dumps(outputs, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--start-month", default="2025-03")
    parser.add_argument("--end-month", default="2026-06")
    parser.add_argument("--funding-start", default="2025-03-27T00:00:00Z")
    parser.add_argument("--funding-end", default="2026-07-01T00:00:00Z")
    args = parser.parse_args()
    prepare(args)


if __name__ == "__main__":
    main()
