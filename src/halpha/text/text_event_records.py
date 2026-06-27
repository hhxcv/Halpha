from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from html import unescape
from json import JSONDecodeError
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.data.raw_artifacts import RawArtifactError, validate_text_events_raw_artifact
from halpha.data.research_data_catalog import write_research_data_catalog
from halpha.storage import write_json
from halpha.text.text_event_history import write_text_event_history


STAGE_NAME = "build_text_event_records"
TEXT_RAW_ARTIFACT = "raw/text_events.json"
TEXT_EVENT_RECORDS_ARTIFACT = "analysis/text_event_records.json"
TEXT_EVENT_RECORDS_ARTIFACT_TYPE = "text_event_records"
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
}
NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)
SPACE_RE = re.compile(r"\s+")


def build_text_event_records(config: dict[str, Any], run: RunContext) -> list[str]:
    text = config.get("text", {})
    if not text.get("enabled"):
        _record_manifest_summary(run, records=[], warnings=[], errors=[], status="skipped")
        return []

    raw = _read_raw_text_events(run)
    records, warnings = normalize_text_event_records(raw)
    errors: list[dict[str, Any]] = []
    artifact = {
        "schema_version": 1,
        "artifact_type": TEXT_EVENT_RECORDS_ARTIFACT_TYPE,
        "run_id": run.run_id,
        "created_at": _utc_timestamp(),
        "source_artifacts": [TEXT_RAW_ARTIFACT],
        "model_states": [],
        "coverage": _coverage(records),
        "records": records,
        "warnings": warnings,
        "errors": errors,
    }

    output_path = run.analysis_dir / "text_event_records.json"
    write_json(output_path, artifact)
    run.manifest["artifacts"]["text_event_records"] = TEXT_EVENT_RECORDS_ARTIFACT
    _record_manifest_summary(run, records=records, warnings=warnings, errors=errors, status="succeeded")
    history_artifacts = write_text_event_history(config, run, records)
    catalog_artifacts = write_research_data_catalog(config, run)
    return [TEXT_EVENT_RECORDS_ARTIFACT, *history_artifacts, *catalog_artifacts]


def normalize_text_event_records(
    raw: dict[str, Any],
    *,
    source_artifact_ref: str = TEXT_RAW_ARTIFACT,
) -> tuple[list[dict[str, Any]], list[str]]:
    source_index = _source_index(raw.get("sources"))
    records = [
        _record_from_item(item, raw=raw, source_index=source_index, source_artifact_ref=source_artifact_ref)
        for item in raw["items"]
    ]
    return records, _artifact_warnings(records, raw)


def _read_raw_text_events(run: RunContext) -> dict[str, Any]:
    raw_path = run.raw_dir / "text_events.json"
    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{TEXT_RAW_ARTIFACT} was not found; collect_text_events must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{TEXT_RAW_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc

    try:
        validate_text_events_raw_artifact(raw, TEXT_RAW_ARTIFACT)
    except RawArtifactError as exc:
        raise PipelineError(str(exc), stage=STAGE_NAME, exit_code=3) from exc
    return raw


def _record_from_item(
    item: dict[str, Any],
    *,
    raw: dict[str, Any],
    source_index: dict[str, str],
    source_artifact_ref: str,
) -> dict[str, Any]:
    warnings: list[str] = []
    raw_item_id = _clean_string(item.get("id"))
    source = _source_from_item(item, source_index=source_index, warnings=warnings)
    title = _clean_string(item.get("title"))
    content_text = _clean_string(item.get("content_text"))
    input_type = _optional_string(item.get("type"), "type", warnings)
    link = _optional_string(item.get("link"), "link", warnings)
    canonical_url = _canonical_url(link, warnings)
    published_at = _optional_string(item.get("published_at"), "published_at", warnings)
    collected_at = _optional_string(raw.get("collected_at"), "collected_at", warnings)
    language = _optional_string(item.get("language"), "language", warnings)
    normalized_title = _normalize_text(title)
    normalized_text = _normalize_text(f"{title} {content_text}")

    return {
        "event_id": _event_id(raw_item_id, source.get("name")),
        "raw_item_id": raw_item_id,
        "input_type": input_type,
        "source": source,
        "title": title,
        "content_text": content_text,
        "link": link,
        "canonical_url": canonical_url,
        "published_at": published_at,
        "collected_at": collected_at,
        "language": language,
        "normalized_title": normalized_title,
        "normalized_text": normalized_text,
        "warnings": warnings,
        "source_artifacts": [source_artifact_ref],
    }


def _source_from_item(
    item: dict[str, Any],
    *,
    source_index: dict[str, str],
    warnings: list[str],
) -> dict[str, str | None]:
    item_source = item.get("source") if isinstance(item.get("source"), dict) else {}
    source_name = _clean_string(item_source.get("name"))
    item_source_url = _clean_optional_string(item_source.get("url"))
    source_url = item_source_url
    if source_url is None:
        source_url = source_index.get(source_name)
        if source_url is None:
            warnings.append(f"source.url is missing from {TEXT_RAW_ARTIFACT}.")
        else:
            warnings.append(f"source.url is missing from item; used artifact source URL from {TEXT_RAW_ARTIFACT}.")
    return {
        "name": source_name,
        "url": source_url,
    }


def _source_index(sources: Any) -> dict[str, str]:
    if not isinstance(sources, list):
        return {}
    index = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        name = _clean_optional_string(source.get("name"))
        url = _clean_optional_string(source.get("url"))
        if name is not None and url is not None:
            index[name] = url
    return index


def _optional_string(value: Any, field: str, warnings: list[str]) -> str | None:
    cleaned = _clean_optional_string(value)
    if cleaned is None:
        warnings.append(f"{field} is missing from {TEXT_RAW_ARTIFACT}.")
    return cleaned


def _clean_string(value: Any) -> str:
    return str(value).strip()


def _clean_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _canonical_url(link: str | None, warnings: list[str]) -> str | None:
    if link is None:
        return None

    parsed = urlparse(link.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        warnings.append("link is not an http or https URL; canonical_url is unavailable.")
        return None

    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_query_param(key)
    ]
    query = urlencode(sorted(query_items), doseq=True)
    netloc = _canonical_netloc(parsed.netloc, parsed.scheme)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), netloc, path, "", query, ""))


def _canonical_netloc(netloc: str, scheme: str) -> str:
    lowered = netloc.lower()
    if scheme.lower() == "http" and lowered.endswith(":80"):
        return lowered[:-3]
    if scheme.lower() == "https" and lowered.endswith(":443"):
        return lowered[:-4]
    return lowered


def _is_tracking_query_param(key: str) -> bool:
    lowered = key.lower()
    return lowered in TRACKING_QUERY_PARAMS or any(lowered.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", unescape(value)).lower()
    normalized = NON_WORD_RE.sub(" ", normalized)
    return SPACE_RE.sub(" ", normalized).strip()


def _event_id(raw_item_id: str, source_name: Any) -> str:
    digest = hashlib.sha256(raw_item_id.encode("utf-8")).hexdigest()[:16]
    return f"text_event:{_source_slug(source_name)}:{digest}"


def _source_slug(source_name: Any) -> str:
    normalized = _normalize_text(str(source_name or "unknown_source"))
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return slug or "unknown_source"


def _artifact_warnings(records: list[dict[str, Any]], raw: dict[str, Any]) -> list[str]:
    warnings = []
    for record in records:
        for warning in record["warnings"]:
            if warning not in warnings:
                warnings.append(warning)
    raw_errors = raw.get("errors")
    if isinstance(raw_errors, list) and raw_errors:
        warnings.append(f"{TEXT_RAW_ARTIFACT} recorded {len(raw_errors)} collection error(s).")
    return warnings


def _coverage(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "raw_items": len(records),
        "records": len(records),
        "records_with_warnings": sum(1 for record in records if record["warnings"]),
        "missing_canonical_url": sum(1 for record in records if record["canonical_url"] is None),
        "missing_published_at": sum(1 for record in records if record["published_at"] is None),
        "missing_language": sum(1 for record in records if record["language"] is None),
    }


def _record_manifest_summary(
    run: RunContext,
    *,
    records: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
    status: str,
) -> None:
    run.manifest["counts"]["text_event_records"] = len(records)
    run.manifest["counts"]["text_event_records_with_warnings"] = sum(
        1 for record in records if record.get("warnings")
    )
    run.manifest["counts"]["text_event_record_warnings"] = sum(
        len(record.get("warnings") or []) for record in records
    )
    run.manifest["counts"]["text_event_record_errors"] = len(errors)
    run.manifest["text_event_records"] = {
        "status": status,
        "records": len(records),
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(UTC)
    timestamp = timestamp.astimezone(UTC).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")
