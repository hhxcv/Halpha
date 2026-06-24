from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from halpha.market.ohlcv_quality import ohlcv_record_invariant_errors
from halpha.storage import write_json


OHLCV_REQUIRED_FIELDS = (
    "source",
    "symbol",
    "timeframe",
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "fetched_at",
)
OHLCV_KEY_FIELDS = ("source", "symbol", "timeframe", "open_time")
OHLCV_ORDER_FIELDS = ("source", "symbol", "timeframe", "open_time")

OHLCV_SCHEMA = pa.schema(
    [
        pa.field("source", pa.string()),
        pa.field("symbol", pa.string()),
        pa.field("timeframe", pa.string()),
        pa.field("open_time", pa.string()),
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("volume", pa.float64()),
        pa.field("fetched_at", pa.string()),
    ]
)


class OHLCVStoreError(Exception):
    """Raised when OHLCV storage input or layout is invalid."""


class OHLCVParquetStore:
    def __init__(self, storage_dir: Path | str, *, run_output_dir: Path | str | None = None) -> None:
        self.storage_dir = Path(storage_dir)
        self.metadata_dir = self.storage_dir.parent / "metadata"
        if run_output_dir is not None:
            _require_outside_run_output_dir(self.storage_dir, Path(run_output_dir))

    def write_records(self, records: Iterable[dict[str, Any]]) -> dict[str, Any]:
        normalized_records = [_normalize_record(record) for record in records]
        if not normalized_records:
            return self._write_metadata()

        groups = sorted({_group_key(record) for record in normalized_records})
        for source, symbol, timeframe in groups:
            existing_records = self.read_records(source=source, symbol=symbol, timeframe=timeframe)
            incoming_records = [
                record
                for record in normalized_records
                if _group_key(record) == (source, symbol, timeframe)
            ]
            merged_records = _deduplicate_records([*existing_records, *incoming_records])
            self._rewrite_group(source, symbol, timeframe, merged_records)

        return self._write_metadata()

    def read_records(
        self,
        *,
        source: str,
        symbol: str,
        timeframe: str,
        deduplicate: bool = True,
    ) -> list[dict[str, Any]]:
        group_dir = self._group_dir(source, symbol, timeframe)
        if not group_dir.exists():
            return []

        records: list[dict[str, Any]] = []
        for parquet_file in sorted(group_dir.rglob("*.parquet")):
            records.extend(_read_parquet_records(parquet_file))
        if deduplicate:
            return _sort_records(_deduplicate_records(records))
        return _sort_records(records)

    def summarize(self) -> dict[str, Any]:
        records = []
        if self.storage_dir.exists():
            for parquet_file in sorted(self.storage_dir.rglob("*.parquet")):
                records.extend(_read_parquet_records(parquet_file))
        return {
            "schema_version": 1,
            "artifact_type": "ohlcv_sync_state",
            "updated_at": _utc_now(),
            "items": _summary_items(self.storage_dir, _deduplicate_records(records)),
        }

    def _rewrite_group(
        self, source: str, symbol: str, timeframe: str, records: list[dict[str, Any]]
    ) -> None:
        group_dir = self._group_dir(source, symbol, timeframe)
        if group_dir.exists():
            for parquet_file in sorted(group_dir.rglob("*.parquet")):
                parquet_file.unlink()

        by_partition: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for record in _sort_records(records):
            opened_at = _parse_iso8601_utc(record["open_time"], "open_time")
            partition = (f"{opened_at.year:04d}", f"{opened_at.month:02d}")
            by_partition.setdefault(partition, []).append(record)

        for (year, month), partition_records in sorted(by_partition.items()):
            partition_dir = group_dir / f"year={year}" / f"month={month}"
            partition_dir.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pylist(partition_records, schema=OHLCV_SCHEMA)
            pq.write_table(table, partition_dir / "part-000.parquet")

    def _write_metadata(self) -> dict[str, Any]:
        summary = self.summarize()
        write_json(
            self.metadata_dir / "ohlcv_schema.json",
            {
                "schema_version": 1,
                "artifact_type": "ohlcv_schema",
                "required_fields": list(OHLCV_REQUIRED_FIELDS),
                "unique_key": list(OHLCV_KEY_FIELDS),
                "time_format": "iso8601_utc",
            },
        )
        write_json(self.metadata_dir / "ohlcv_sync_state.json", summary)
        return summary

    def _group_dir(self, source: str, symbol: str, timeframe: str) -> Path:
        return self.storage_dir / f"source={source}" / f"symbol={symbol}" / f"timeframe={timeframe}"


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise OHLCVStoreError("ohlcv record must be a mapping.")

    normalized: dict[str, Any] = {}
    for field in OHLCV_REQUIRED_FIELDS:
        if field not in record:
            raise OHLCVStoreError(f"ohlcv record missing required field: {field}.")

    for field in ("source", "symbol", "timeframe"):
        normalized[field] = _require_non_empty_string(record[field], field)
    normalized["open_time"] = _format_iso8601_utc(record["open_time"], "open_time")
    for field in ("open", "high", "low", "close", "volume"):
        normalized[field] = _require_number(record[field], field)
    normalized["fetched_at"] = _format_iso8601_utc(record["fetched_at"], "fetched_at")
    invariant_errors = ohlcv_record_invariant_errors(normalized)
    if invariant_errors:
        raise OHLCVStoreError(invariant_errors[0])
    return normalized


def _require_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OHLCVStoreError(f"{field} must be a non-empty string.")
    return value.strip()


def _require_number(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise OHLCVStoreError(f"{field} must be a number.")
    number = float(value)
    if not isfinite(number):
        raise OHLCVStoreError(f"{field} must be a finite number.")
    return number


def _format_iso8601_utc(value: Any, field: str) -> str:
    parsed = _parse_iso8601_utc(value, field)
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso8601_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise OHLCVStoreError(f"{field} must be an ISO 8601 UTC string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OHLCVStoreError(f"{field} must be an ISO 8601 UTC string.") from exc
    if parsed.tzinfo is None:
        raise OHLCVStoreError(f"{field} must include a UTC offset.")
    return parsed.astimezone(timezone.utc)


def _read_parquet_records(path: Path) -> list[dict[str, Any]]:
    table = pq.ParquetFile(path).read()
    records = table.to_pylist()
    return [_normalize_record(record) for record in records]


def _deduplicate_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in records:
        key = _record_key(record)
        existing = deduplicated.get(key)
        if existing is not None and _ohlcv_values(existing) != _ohlcv_values(record):
            raise OHLCVStoreError(
                "duplicate ohlcv record has conflicting values for "
                f"source={key[0]}, symbol={key[1]}, timeframe={key[2]}, open_time={key[3]}."
            )
        deduplicated[key] = record
    return _sort_records(deduplicated.values())


def _sort_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: tuple(record[field] for field in OHLCV_ORDER_FIELDS))


def _group_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (record["source"], record["symbol"], record["timeframe"])


def _record_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (record["source"], record["symbol"], record["timeframe"], record["open_time"])


def _ohlcv_values(record: dict[str, Any]) -> tuple[float, float, float, float, float]:
    return (record["open"], record["high"], record["low"], record["close"], record["volume"])


def _summary_items(storage_dir: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in _sort_records(records):
        groups.setdefault(_group_key(record), []).append(record)

    items = []
    for (source, symbol, timeframe), group_records in sorted(groups.items()):
        ordered = _sort_records(group_records)
        items.append(
            {
                "source": source,
                "symbol": symbol,
                "timeframe": timeframe,
                "earliest_open_time": ordered[0]["open_time"],
                "latest_open_time": ordered[-1]["open_time"],
                "row_count": len(ordered),
                "storage_ref": _storage_ref(storage_dir, source, symbol, timeframe),
                "warnings": [],
            }
        )
    return items


def _storage_ref(storage_dir: Path, source: str, symbol: str, timeframe: str) -> str:
    return (
        storage_dir / f"source={source}" / f"symbol={symbol}" / f"timeframe={timeframe}"
    ).as_posix()


def _require_outside_run_output_dir(storage_dir: Path, run_output_dir: Path) -> None:
    storage_path = storage_dir.resolve()
    run_path = run_output_dir.resolve()
    if storage_path == run_path or run_path in storage_path.parents:
        raise OHLCVStoreError("ohlcv storage root must be outside run output directory.")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
