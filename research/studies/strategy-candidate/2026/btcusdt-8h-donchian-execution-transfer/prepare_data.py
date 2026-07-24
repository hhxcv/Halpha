"""Prepare immutable BTCUSDT USD-M 8h inputs with official checksums."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType


STUDY_DIR = Path(__file__).resolve().parent
BASE_PATH = STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "prepare_data.py"
ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/8h"
MARK_BASE = "https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/8h"


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location("halpha_btc_8h_prepare_base", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_PREPARE_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base()


def prepare(args: argparse.Namespace) -> None:
    root = Path(args.cache_root).resolve()
    months = BASE._month_range(args.start_month, args.end_month)
    archives = BASE._prepare_archives(
        cache_root=root,
        relative_root="klines-8h",
        base_url=ARCHIVE_BASE,
        name_template="BTCUSDT-8h-{month}.zip",
        months=months,
    )
    mark_archives = BASE._prepare_archives(
        cache_root=root,
        relative_root="mark-price-klines-8h",
        base_url=MARK_BASE,
        name_template="BTCUSDT-8h-{month}.zip",
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
    funding = BASE._funding_history(start_ms, end_ms)
    funding_path = root / "funding-rate-history.json"
    funding_path.write_text(
        json.dumps(funding, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "venue": "Binance USD-M",
        "instrument": "BTCUSDT perpetual",
        "interval": "8h",
        "archives": archives,
        "mark_price_archives": mark_archives,
        "funding_snapshot": {
            "url": BASE.FUNDING_URL,
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
    prepare(parser.parse_args())


if __name__ == "__main__":
    main()
