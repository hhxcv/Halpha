"""Prepare immutable ETHUSDT USD-M inputs using the prior audited downloader helpers."""

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
BASE_PREPARE_PATH = STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "prepare_data.py"
SYMBOL = "ETHUSDT"
ARCHIVE_BASE = f"https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/1d"
MARK_ARCHIVE_BASE = (
    f"https://data.binance.vision/data/futures/um/monthly/markPriceKlines/{SYMBOL}/8h"
)
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location("halpha_eth_prepare_base", BASE_PREPARE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_PREPARE_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base()


def _funding_history(start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cursor = start_ms
    while cursor < end_ms:
        query = urllib.parse.urlencode(
            {
                "symbol": SYMBOL,
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
                        "symbol": str(item.get("symbol", SYMBOL)),
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


def prepare(args: argparse.Namespace) -> None:
    root = Path(args.cache_root).resolve()
    months = BASE._month_range(args.start_month, args.end_month)
    archives = BASE._prepare_archives(
        cache_root=root,
        relative_root="klines-1d",
        base_url=ARCHIVE_BASE,
        name_template=f"{SYMBOL}-1d-{{month}}.zip",
        months=months,
    )
    mark_archives = BASE._prepare_archives(
        cache_root=root,
        relative_root="mark-price-klines-8h",
        base_url=MARK_ARCHIVE_BASE,
        name_template=f"{SYMBOL}-8h-{{month}}.zip",
        months=months,
    )
    start_ms = int(
        datetime.fromisoformat(args.funding_start.replace("Z", "+00:00")).timestamp()
        * 1000
    )
    end_ms = int(
        datetime.fromisoformat(args.funding_end.replace("Z", "+00:00")).timestamp()
        * 1000
    )
    funding = _funding_history(start_ms, end_ms)
    funding_path = root / "funding-rate-history.json"
    funding_path.write_text(
        json.dumps(funding, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "venue": "Binance USD-M",
        "instrument": "ETHUSDT perpetual",
        "interval": "1d",
        "archives": archives,
        "mark_price_archives": mark_archives,
        "funding_snapshot": {
            "url": FUNDING_URL,
            "requested_start": args.funding_start,
            "requested_end_exclusive": args.funding_end,
            "cache_relative_path": funding_path.relative_to(root).as_posix(),
            "sha256": BASE._sha256(funding_path),
            "records": len(funding),
            "first_funding_time": funding[0]["fundingTime"] if funding else None,
            "last_funding_time": funding[-1]["fundingTime"] if funding else None,
        },
    }
    manifest_path = root / "source_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "manifest_sha256": BASE._sha256(manifest_path),
                "archives": len(archives),
                "mark_price_archives": len(mark_archives),
                "funding_records": len(funding),
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--start-month", default="2020-01")
    parser.add_argument("--end-month", default="2026-06")
    parser.add_argument("--funding-start", default="2019-09-01T00:00:00Z")
    parser.add_argument("--funding-end", default="2026-07-01T00:00:00Z")
    parser.set_defaults(func=prepare)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
