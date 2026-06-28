from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from halpha.data.event_like_query import EventLikeQueryError, query_event_like_records
from halpha.market.ohlcv_query import OHLCVQueryError, query_ohlcv_records
from halpha.storage import display_path, resolve_runtime_path, runtime_root, write_json


DATA_EXPORT_SCHEMA_VERSION = 1
EVENT_LIKE_DATA_TYPES = {"text_event", "macro_calendar", "onchain_flow", "derivatives_market", "market_anomaly"}
OHLCV_EXPORT_FORMATS = {"csv", "parquet"}
EVENT_LIKE_EXPORT_FORMATS = {"csv", "json"}


class DataExportError(Exception):
    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def export_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    data_type: str,
    output_path: Path | str,
    output_format: str,
    start: str,
    end: str,
    source: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    identity: dict[str, Any] | None = None,
    as_of: str | None = None,
    limit: int | None = None,
    sort_order: str = "asc",
    now: datetime | str | None = None,
) -> dict[str, Any]:
    normalized_data_type = str(data_type or "").strip()
    normalized_format = str(output_format or "").strip().lower()
    if not start or not end:
        raise DataExportError("data export requires explicit start and end timestamps.", exit_code=2)
    if normalized_data_type == "ohlcv":
        _require_supported_format(normalized_format, OHLCV_EXPORT_FORMATS, data_type=normalized_data_type)
    elif normalized_data_type in EVENT_LIKE_DATA_TYPES:
        _require_supported_format(normalized_format, EVENT_LIKE_EXPORT_FORMATS, data_type=normalized_data_type)
    else:
        supported = ", ".join(["ohlcv", *sorted(EVENT_LIKE_DATA_TYPES)])
        raise DataExportError(f"unsupported data_type {normalized_data_type}. Supported: {supported}.", exit_code=2)

    output = resolve_runtime_path(Path(output_path), config_path=config_path)
    query_result = _query_records(
        config,
        config_path=config_path,
        data_type=normalized_data_type,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        identity=identity,
        start=start,
        end=end,
        as_of=as_of,
        limit=limit,
        sort_order=sort_order,
    )
    records = [record for record in query_result.get("records", []) if isinstance(record, dict)]
    metadata = _export_metadata(
        data_type=normalized_data_type,
        output_format=normalized_format,
        output_path=output,
        query_result=query_result,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        identity=identity,
        start=start,
        end=end,
        as_of=as_of,
        limit=limit,
        sort_order=sort_order,
        now=now,
    )

    metadata_path: Path | None
    if normalized_data_type == "ohlcv":
        metadata_path = _metadata_sidecar_path(output)
        if normalized_format == "csv":
            _write_csv(output, records)
        else:
            _write_parquet(output, records)
    else:
        if normalized_format == "json":
            metadata_path = None
        else:
            metadata_path = _metadata_sidecar_path(output)
            _write_csv(output, records)

    metadata_ref = _display_ref(metadata_path, config_path=config_path) if metadata_path is not None else None
    metadata["metadata_path"] = metadata_ref
    if metadata_path is not None:
        _write_metadata_sidecar(metadata_path, metadata)
    elif normalized_format == "json":
        _write_json_export(output, metadata=metadata, records=records)

    return {
        "schema_version": DATA_EXPORT_SCHEMA_VERSION,
        "artifact_type": "data_export_result",
        "status": "warning" if metadata["warnings"] or metadata["errors"] else "ok",
        "data_type": normalized_data_type,
        "format": normalized_format,
        "output_path": _display_ref(output, config_path=config_path),
        "metadata_path": metadata_ref,
        "record_count": metadata["record_count"],
        "matched_record_count": metadata["matched_record_count"],
        "truncated": metadata["truncated"],
        "query_parameters": metadata["query_parameters"],
        "coverage_diagnostics": metadata["coverage_diagnostics"],
        "warnings": metadata["warnings"],
        "errors": metadata["errors"],
        "source_artifacts": metadata["source_artifacts"],
    }


def _query_records(
    config: dict[str, Any],
    *,
    config_path: Path,
    data_type: str,
    source: str | None,
    symbol: str | None,
    timeframe: str | None,
    identity: dict[str, Any] | None,
    start: str,
    end: str,
    as_of: str | None,
    limit: int | None,
    sort_order: str,
) -> dict[str, Any]:
    try:
        if data_type == "ohlcv":
            if not source or not symbol or not timeframe:
                raise DataExportError(
                    "data export --data-type ohlcv requires --source, --symbol, and --timeframe.",
                    exit_code=2,
                )
            return query_ohlcv_records(
                _ohlcv_storage_dir(config, config_path=config_path),
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                as_of=as_of,
                config_path=config_path,
                limit=limit,
            )
        return query_event_like_records(
            config_path,
            data_type=data_type,
            source=source,
            identity=identity,
            start=start,
            end=end,
            as_of=as_of,
            limit=limit,
            sort_order=sort_order,
        )
    except DataExportError:
        raise
    except (OHLCVQueryError, EventLikeQueryError) as exc:
        raise DataExportError(str(exc), exit_code=exc.exit_code) from exc


def _ohlcv_storage_dir(config: dict[str, Any], *, config_path: Path) -> Path:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    storage_dir = ohlcv.get("storage_dir")
    if not isinstance(storage_dir, str) or not storage_dir.strip():
        raise DataExportError("market.ohlcv.storage_dir must be configured for OHLCV export.", exit_code=2)
    return resolve_runtime_path(storage_dir, config_path=config_path)


def _export_metadata(
    *,
    data_type: str,
    output_format: str,
    output_path: Path,
    query_result: dict[str, Any],
    source: str | None,
    symbol: str | None,
    timeframe: str | None,
    identity: dict[str, Any] | None,
    start: str,
    end: str,
    as_of: str | None,
    limit: int | None,
    sort_order: str,
    now: datetime | str | None,
) -> dict[str, Any]:
    warnings = [item for item in query_result.get("warnings", [])]
    errors = [item for item in query_result.get("errors", [])]
    return {
        "schema_version": DATA_EXPORT_SCHEMA_VERSION,
        "artifact_type": "data_export_metadata",
        "created_at": _format_utc(now),
        "data_type": data_type,
        "format": output_format,
        "output_path": _display_ref(output_path),
        "metadata_path": None,
        "query_parameters": {
            "data_type": data_type,
            "source": source,
            "symbol": symbol,
            "timeframe": timeframe,
            "identity": _normalized_identity(identity),
            "start": start,
            "end": end,
            "as_of": as_of,
            "limit": limit,
            "sort_order": sort_order if data_type != "ohlcv" else None,
        },
        "query": _query_metadata(query_result),
        "record_count": int(query_result.get("record_count") or 0),
        "matched_record_count": int(query_result.get("matched_record_count") or 0),
        "history_row_count": int(query_result.get("history_row_count") or 0),
        "truncated": bool(query_result.get("truncated")),
        "coverage_diagnostics": query_result.get("coverage_diagnostics") or {},
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": [str(item) for item in query_result.get("source_artifacts", []) if isinstance(item, str)],
    }


def _query_metadata(query_result: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "artifact_type",
        "status",
        "query_mode",
        "data_type",
        "source",
        "symbol",
        "timeframe",
        "identity",
        "requested_start",
        "requested_end",
        "as_of",
        "sort_order",
        "time_fields",
        "range",
        "matched_record_count",
        "record_count",
        "history_row_count",
        "truncated",
        "limit",
        "missing_diagnostics",
        "filter_diagnostics",
        "empty_result_diagnostics",
        "quality",
    )
    return {key: query_result.get(key) for key in keys if key in query_result}


def _require_supported_format(output_format: str, supported: set[str], *, data_type: str) -> None:
    if output_format not in supported:
        choices = ", ".join(sorted(supported))
        raise DataExportError(f"{data_type} export format must be one of: {choices}.", exit_code=2)


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _csv_fieldnames(records)
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not fieldnames:
            return
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in fieldnames})


def _write_parquet(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(records)
    pq.write_table(table, path)


def _write_json_export(path: Path, *, metadata: dict[str, Any], records: list[dict[str, Any]]) -> None:
    write_json(
        path,
        {
            "schema_version": DATA_EXPORT_SCHEMA_VERSION,
            "artifact_type": "data_export",
            "metadata": metadata,
            "records": records,
        },
    )


def _write_metadata_sidecar(path: Path, metadata: dict[str, Any]) -> None:
    write_json(path, metadata)


def _metadata_sidecar_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.metadata.json")


def _csv_fieldnames(records: list[dict[str, Any]]) -> list[str]:
    fieldnames: set[str] = set()
    for record in records:
        fieldnames.update(str(key) for key in record)
    return sorted(fieldnames)


def _csv_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return _json_string(value)


def _normalized_identity(identity: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(identity, dict):
        return {}
    return {
        str(key): str(identity[key])
        for key in sorted(identity)
        if identity[key] is not None and str(identity[key]) != ""
    }


def _json_string(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _display_ref(path: Path | None, *, config_path: Path | None = None) -> str:
    if path is None:
        return ""
    return display_path(path, base=runtime_root(config_path))


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise DataExportError("export timestamps must include a UTC offset.", exit_code=2)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DataExportError("export timestamps must be valid ISO 8601 strings.", exit_code=2) from exc
        if timestamp.tzinfo is None:
            raise DataExportError("export timestamps must include a UTC offset.", exit_code=2)
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise DataExportError("export timestamps must be datetimes or ISO 8601 strings.", exit_code=2)
    return timestamp.isoformat().replace("+00:00", "Z")
