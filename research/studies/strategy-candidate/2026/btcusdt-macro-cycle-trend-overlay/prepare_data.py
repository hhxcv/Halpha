"""Freeze Coin Metrics BTC daily price and MVRV inputs outside Git."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


API_ROOT = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _content_identity(rows: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "time": item["time"],
            "PriceUSD": item["PriceUSD"],
            "CapMVRVCur": item["CapMVRVCur"],
        }
        for item in rows
    ]
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default="2026-07-01")
    parser.add_argument("--output-manifest", required=True)
    args = parser.parse_args()

    query = urllib.parse.urlencode(
        {
            "assets": "btc",
            "metrics": "PriceUSD,CapMVRVCur",
            "frequency": "1d",
            "start_time": args.start,
            "end_time": args.end,
            "page_size": 10000,
        }
    )
    url = f"{API_ROOT}?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "HalphaResearch/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    payload = json.loads(raw)
    if payload.get("next_page_url"):
        raise ValueError("UNEXPECTED_PAGINATION")
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError("EMPTY_COIN_METRICS_DATA")
    for item in rows:
        if not all(key in item for key in ("time", "PriceUSD", "CapMVRVCur")):
            raise ValueError("MISSING_REQUIRED_METRIC")

    cache_root = Path(args.cache_root).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    filename = f"coinmetrics-btc-{args.start}_{args.end}.json"
    raw_path = cache_root / filename
    raw_path.write_bytes(raw)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source": "Coin Metrics Community API v4",
        "request_url": url,
        "asset": "btc",
        "metrics": ["PriceUSD", "CapMVRVCur"],
        "frequency": "1d",
        "requested_period": [args.start, args.end],
        "row_count": len(rows),
        "first_time": rows[0]["time"],
        "last_time": rows[-1]["time"],
        "cache_root": str(cache_root),
        "cache_relative_path": filename,
        "raw_sha256": _sha256_bytes(raw),
        "content_identity": _content_identity(rows),
    }
    output = Path(args.output_manifest).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
