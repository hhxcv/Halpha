"""Prepare immutable public Binance inputs for the daily Donchian study."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1d"
MARK_ARCHIVE_BASE = (
    "https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/8h"
)
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path, *, retries: int = 4) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "HalphaResearch/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                temporary.write_bytes(response.read())
            temporary.replace(target)
            return
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt + 1 == retries:
                raise
            time.sleep(2**attempt)


def _month_range(start: str, end: str) -> list[str]:
    cursor = datetime.strptime(start, "%Y-%m").replace(tzinfo=UTC)
    end_dt = datetime.strptime(end, "%Y-%m").replace(tzinfo=UTC)
    months: list[str] = []
    while cursor <= end_dt:
        months.append(cursor.strftime("%Y-%m"))
        year = cursor.year + (1 if cursor.month == 12 else 0)
        month = 1 if cursor.month == 12 else cursor.month + 1
        cursor = cursor.replace(year=year, month=month)
    return months


def _read_checksum(path: Path, expected_name: str) -> str:
    parts = path.read_text(encoding="utf-8").strip().split()
    if len(parts) < 2 or parts[1].lstrip("*") != expected_name:
        raise ValueError(f"CHECKSUM_FORMAT_INVALID:{path}")
    digest = parts[0].lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"CHECKSUM_DIGEST_INVALID:{path}")
    return digest


def _get_json(url: str, *, retries: int = 4) -> Any:
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "HalphaResearch/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            if attempt + 1 == retries:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _prepare_archives(
    *,
    cache_root: Path,
    relative_root: str,
    base_url: str,
    name_template: str,
    months: list[str],
) -> list[dict[str, Any]]:
    archive_root = cache_root / relative_root
    archives: list[dict[str, Any]] = []
    for month in months:
        name = name_template.format(month=month)
        archive_url = f"{base_url}/{name}"
        checksum_url = f"{archive_url}.CHECKSUM"
        archive_path = archive_root / name
        checksum_path = archive_root / f"{name}.CHECKSUM"
        if not archive_path.is_file():
            _download(archive_url, archive_path)
        if not checksum_path.is_file():
            _download(checksum_url, checksum_path)
        expected = _read_checksum(checksum_path, name)
        actual = _sha256(archive_path)
        if actual != expected:
            raise ValueError(f"ARCHIVE_SHA256_MISMATCH:{name}")
        archives.append(
            {
                "month": month,
                "url": archive_url,
                "checksum_url": checksum_url,
                "cache_relative_path": archive_path.relative_to(cache_root).as_posix(),
                "checksum_relative_path": checksum_path.relative_to(cache_root).as_posix(),
                "sha256": actual,
                "bytes": archive_path.stat().st_size,
            }
        )
    return archives


def _funding_history(start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cursor = start_ms
    while cursor < end_ms:
        query = urllib.parse.urlencode(
            {
                "symbol": "BTCUSDT",
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": 1000,
            }
        )
        page = _get_json(f"{FUNDING_URL}?{query}")
        if not isinstance(page, list):
            raise ValueError("FUNDING_RESPONSE_NOT_LIST")
        if not page:
            break
        for item in page:
            timestamp = int(item["fundingTime"])
            if start_ms <= timestamp < end_ms:
                records.append(
                    {
                        "symbol": str(item.get("symbol", "BTCUSDT")),
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
    cache_root = Path(args.cache_root).resolve()
    months = _month_range(args.start_month, args.end_month)
    archives = _prepare_archives(
        cache_root=cache_root,
        relative_root="klines-1d",
        base_url=ARCHIVE_BASE,
        name_template="BTCUSDT-1d-{month}.zip",
        months=months,
    )
    mark_archives = _prepare_archives(
        cache_root=cache_root,
        relative_root="mark-price-klines-8h",
        base_url=MARK_ARCHIVE_BASE,
        name_template="BTCUSDT-8h-{month}.zip",
        months=months,
    )

    funding_start = int(
        datetime.fromisoformat(args.funding_start.replace("Z", "+00:00")).timestamp() * 1000
    )
    funding_end = int(
        datetime.fromisoformat(args.funding_end.replace("Z", "+00:00")).timestamp() * 1000
    )
    funding = _funding_history(funding_start, funding_end)
    funding_path = cache_root / "funding-rate-history.json"
    funding_path.write_text(
        json.dumps(funding, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "venue": "Binance USD-M",
        "instrument": "BTCUSDT perpetual",
        "interval": "1d",
        "archives": archives,
        "mark_price_archives": mark_archives,
        "funding_snapshot": {
            "url": FUNDING_URL,
            "requested_start": args.funding_start,
            "requested_end_exclusive": args.funding_end,
            "cache_relative_path": funding_path.relative_to(cache_root).as_posix(),
            "sha256": _sha256(funding_path),
            "records": len(funding),
            "first_funding_time": funding[0]["fundingTime"] if funding else None,
            "last_funding_time": funding[-1]["fundingTime"] if funding else None,
        },
    }
    manifest_path = cache_root / "source_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "manifest_sha256": _sha256(manifest_path),
                "archives": len(archives),
                "mark_price_archives": len(mark_archives),
                "archive_bytes": sum(item["bytes"] for item in archives),
                "mark_price_archive_bytes": sum(item["bytes"] for item in mark_archives),
                "funding_records": len(funding),
            },
            ensure_ascii=False,
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
