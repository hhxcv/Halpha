"""Prepare immutable Binance Spot daily archives for the fixed Donchian study."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


BASE_URL = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _months(start: str, end: str) -> list[str]:
    start_year, start_month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    result: list[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return result


def _download(url: str, target: Path) -> None:
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "HalphaResearch/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                target.write_bytes(response.read())
            return
        except Exception:
            if attempt == 3:
                raise
            time.sleep(0.5 * (2**attempt))


def prepare(args: argparse.Namespace) -> None:
    root = Path(args.cache_root).resolve()
    archives: list[dict[str, object]] = []
    for month in _months(args.start_month, args.end_month):
        name = f"BTCUSDT-1d-{month}.zip"
        url = f"{BASE_URL}/{name}"
        target = root / "klines-1d" / name
        checksum_target = target.with_suffix(target.suffix + ".CHECKSUM")
        _download(url, target)
        _download(f"{url}.CHECKSUM", checksum_target)
        checksum_text = checksum_target.read_text(encoding="utf-8").strip().split()[0].lower()
        actual = _sha256(target)
        if actual != checksum_text:
            raise ValueError(f"CHECKSUM_MISMATCH:{name}")
        archives.append(
            {
                "month": month,
                "url": url,
                "checksum_url": f"{url}.CHECKSUM",
                "cache_relative_path": target.relative_to(root).as_posix(),
                "sha256": actual,
                "bytes": target.stat().st_size,
            }
        )
    identity_payload = {
        "market": "BINANCE_SPOT",
        "symbol": "BTCUSDT",
        "interval": "1d",
        "archives": archives,
    }
    identity = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        **identity_payload,
        "archive_count": len(archives),
        "total_bytes": sum(int(item["bytes"]) for item in archives),
        "content_identity": identity,
    }
    (root / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"archives": len(archives), "content_identity": identity}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--start-month", default="2020-01")
    parser.add_argument("--end-month", default="2026-06")
    parser.set_defaults(func=prepare)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
