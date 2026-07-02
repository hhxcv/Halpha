from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from json import JSONDecodeError
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from halpha.data.public_capabilities import unsupported_macro_calendar_raw_collection_reason
from halpha.data.raw_artifacts import RawArtifactError, validate_macro_calendar_raw_artifact
from halpha.runtime.pipeline_contracts import RunContext
from halpha.runtime.public_http import market_proxy_url_from_config, urlopen_from_public_proxy
from halpha.runtime.public_rate_limits import (
    PublicApiRateLimitError,
    is_public_api_rate_limit_response,
    record_public_api_rate_limit,
    retry_after_seconds_from_headers,
)
from halpha.storage import write_json


STAGE_NAME = "collect_macro_calendar_data"
MACRO_CALENDAR_ARTIFACT = "raw/macro_calendar.json"
FEDERAL_RESERVE_FOMC_SOURCE = "federal_reserve_fomc"
FEDERAL_RESERVE_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BEA_RELEASE_CALENDAR_SOURCE = "bea_release_calendar"
BEA_RELEASE_DATES_URL = "https://apps.bea.gov/API/signup/release_dates.json"
REQUEST_TIMEOUT_SECONDS = 20
SOURCE_TIMEZONE = "America/New_York"
FOMC_ENDPOINT = "fomc_calendars"
BEA_ENDPOINT = "bea_release_dates_json"
DATE_PRECISION_WARNING = (
    "source provides FOMC meeting dates without exact intraday time; "
    "scheduled_at is normalized to the meeting end date at 00:00:00Z."
)
BEA_HIGH_IMPORTANCE_RELEASES = {
    "Corporate Profits",
    "Gross Domestic Product",
    "Personal Income and Outlays",
    "U.S. International Trade in Goods and Services",
}

MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}
MONTH_ALIASES = {
    "Jan": "January",
    "Feb": "February",
    "Mar": "March",
    "Apr": "April",
    "Jun": "June",
    "Jul": "July",
    "Aug": "August",
    "Sep": "September",
    "Sept": "September",
    "Oct": "October",
    "Nov": "November",
    "Dec": "December",
}
DATE_LABEL_RE = re.compile(r"^(?P<start>\d{1,2})(?:-(?P<end>\d{1,2}))?(?P<sep>\*)?(?:\s+\(notation vote\))?$")
YEAR_HEADING_RE = re.compile(r"^(?P<year>20\d{2}) FOMC Meetings$")


def collect_macro_calendar_data(config: dict[str, Any], run: RunContext) -> list[str]:
    macro_calendar = _macro_calendar_config(config)
    if not macro_calendar.get("enabled"):
        run.manifest["macro_calendar"] = {
            "status": "skipped",
            "reason": "macro_calendar is disabled or not configured",
        }
        _record_manifest_counts(run, items=[], availability=[], errors=[])
        return []

    raw = collect_macro_calendar_raw(
        macro_calendar,
        affected_assets=_market_symbols(config),
        proxy_url=market_proxy_url_from_config(config, error_factory=MacroCalendarCollectionError),
        rate_limit_config_path=run.config_path,
    )
    artifact_path = run.raw_dir / "macro_calendar.json"
    write_json(artifact_path, raw)
    run.manifest["artifacts"]["raw_macro_calendar"] = MACRO_CALENDAR_ARTIFACT
    run.manifest["macro_calendar"] = _manifest_summary(raw)
    _record_manifest_counts(run, items=raw["items"], availability=raw["availability"], errors=raw["errors"])
    return [MACRO_CALENDAR_ARTIFACT]


def collect_macro_calendar_raw(
    macro_calendar: dict[str, Any],
    *,
    affected_assets: list[str] | None = None,
    proxy_url: str | None = None,
    now: datetime | None = None,
    rate_limit_config_path: Path | None = None,
) -> dict[str, Any]:
    now_value = _utc_now() if now is None else now.astimezone(timezone.utc)
    collected_at = _utc_timestamp(now_value)
    sources = _macro_calendar_sources(macro_calendar)
    source_urls = _macro_calendar_source_urls(macro_calendar, sources)
    lookback_days = _positive_int(macro_calendar.get("lookback_days"), default=7)
    lookahead_days = _positive_int(macro_calendar.get("lookahead_days"), default=45)
    window_start = now_value - timedelta(days=lookback_days)
    window_end = now_value + timedelta(days=lookahead_days)
    data_classes = _string_list(macro_calendar.get("data_classes"))
    raw = _raw_artifact(
        sources[0] if len(sources) == 1 else "multiple",
        source_urls.get(sources[0], "") if len(sources) == 1 else "",
        collected_at,
        window_start=_utc_timestamp(window_start),
        window_end=_utc_timestamp(window_end),
        sources=[{"name": source, "url": source_urls.get(source, "")} for source in sources],
    )

    multi_source = len(sources) > 1
    for source in sources:
        source_data_classes = _requested_data_classes_for_source(
            source,
            data_classes=data_classes,
            multi_source=multi_source,
        )
        if not source_data_classes:
            continue
        result = _collect_macro_calendar_source(
            source,
            source_url=source_urls.get(source, ""),
            data_classes=source_data_classes,
            collected_at=collected_at,
            window_start=window_start,
            window_end=window_end,
            affected_assets=affected_assets or [],
            proxy_url=proxy_url,
            rate_limit_config_path=rate_limit_config_path,
        )
        raw["items"].extend(result["items"])
        raw["availability"].extend(result["availability"])
        raw["errors"].extend(result["errors"])

    try:
        validate_macro_calendar_raw_artifact(raw, MACRO_CALENDAR_ARTIFACT)
    except RawArtifactError as exc:
        raw["errors"].append(_collector_error(source="macro_calendar", message=str(exc), source_url=""))
    return raw


def _collect_macro_calendar_source(
    source: str,
    *,
    source_url: str,
    data_classes: list[str],
    collected_at: str,
    window_start: datetime,
    window_end: datetime,
    affected_assets: list[str],
    proxy_url: str | None,
    rate_limit_config_path: Path | None,
) -> dict[str, list[dict[str, Any]]]:
    if source == FEDERAL_RESERVE_FOMC_SOURCE:
        return _collect_fomc_source(
            source=source,
            source_url=source_url,
            data_classes=data_classes,
            collected_at=collected_at,
            window_start=window_start,
            window_end=window_end,
            affected_assets=affected_assets,
            proxy_url=proxy_url,
            rate_limit_config_path=rate_limit_config_path,
        )
    if source == BEA_RELEASE_CALENDAR_SOURCE:
        return _collect_bea_release_calendar_source(
            source=source,
            source_url=source_url,
            data_classes=data_classes,
            collected_at=collected_at,
            window_start=window_start,
            window_end=window_end,
            affected_assets=affected_assets,
            proxy_url=proxy_url,
            rate_limit_config_path=rate_limit_config_path,
        )
    availability = [
        _availability_record(
            source=source,
            data_class=data_class,
            status="unavailable",
            reason=unsupported_macro_calendar_raw_collection_reason(data_class, source),
        )
        for data_class in (data_classes or ["central_bank_event"])
    ]
    return {"items": [], "availability": availability, "errors": []}


def _collect_fomc_source(
    *,
    source: str,
    source_url: str,
    data_classes: list[str],
    collected_at: str,
    window_start: datetime,
    window_end: datetime,
    affected_assets: list[str],
    proxy_url: str | None,
    rate_limit_config_path: Path | None,
) -> dict[str, list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    availability: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for data_class in data_classes:
        if data_class != "central_bank_event":
            availability.append(
                _availability_record(
                    source=source,
                    data_class=data_class,
                    status="unavailable",
                    reason=unsupported_macro_calendar_raw_collection_reason(data_class, source),
                )
            )

    if "central_bank_event" not in data_classes:
        availability.append(
            _availability_record(
                source=source,
                data_class="central_bank_event",
                status="skipped",
                reason="central_bank_event is not configured.",
            )
        )
        return {"items": items, "availability": availability, "errors": errors}

    try:
        body = _request_source(
            source_url,
            proxy_url=proxy_url,
            rate_limit_config_path=rate_limit_config_path,
            rate_limit_source=source,
        )
    except MacroCalendarCollectionError as exc:
        error = _collector_error(source=source, message=str(exc), source_url=source_url)
        errors.append(error)
        availability.append(
            _availability_record(
                source=source,
                data_class="central_bank_event",
                status="failed",
                endpoint=FOMC_ENDPOINT,
                error_count=1,
                reason=str(exc),
            )
        )
        return {"items": items, "availability": availability, "errors": errors}

    records, parse_errors = _parse_federal_reserve_fomc(
        body,
        source=source,
        source_url=source_url,
        collected_at=collected_at,
        affected_assets=affected_assets,
    )
    windowed_records = [record for record in records if _inside_window(record["scheduled_at"], window_start, window_end)]
    items.extend(windowed_records)
    errors.extend(parse_errors)
    availability.append(
        _availability_record(
            source=source,
            data_class="central_bank_event",
            status=_availability_status(
                records=records,
                windowed_records=windowed_records,
                errors=parse_errors,
                window_start=window_start,
            ),
            endpoint=FOMC_ENDPOINT,
            record_count=len(windowed_records),
            parsed_record_count=len(records),
            error_count=len(parse_errors),
        )
    )
    return {"items": items, "availability": availability, "errors": errors}


def _collect_bea_release_calendar_source(
    *,
    source: str,
    source_url: str,
    data_classes: list[str],
    collected_at: str,
    window_start: datetime,
    window_end: datetime,
    affected_assets: list[str],
    proxy_url: str | None,
    rate_limit_config_path: Path | None,
) -> dict[str, list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    availability: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for data_class in data_classes:
        if data_class != "economic_release":
            availability.append(
                _availability_record(
                    source=source,
                    data_class=data_class,
                    status="unavailable",
                    reason=unsupported_macro_calendar_raw_collection_reason(data_class, source),
                )
            )

    if "economic_release" not in data_classes:
        availability.append(
            _availability_record(
                source=source,
                data_class="economic_release",
                status="skipped",
                reason="economic_release is not configured.",
            )
        )
        return {"items": items, "availability": availability, "errors": errors}

    try:
        body = _request_source(
            source_url,
            proxy_url=proxy_url,
            rate_limit_config_path=rate_limit_config_path,
            rate_limit_source=source,
        )
    except MacroCalendarCollectionError as exc:
        error = _collector_error(source=source, message=str(exc), source_url=source_url)
        errors.append(error)
        availability.append(
            _availability_record(
                source=source,
                data_class="economic_release",
                status="failed",
                endpoint=BEA_ENDPOINT,
                error_count=1,
                reason=str(exc),
            )
        )
        return {"items": items, "availability": availability, "errors": errors}

    records, parse_errors = _parse_bea_release_dates(
        body,
        source=source,
        source_url=source_url,
        collected_at=collected_at,
        affected_assets=affected_assets,
    )
    windowed_records = [record for record in records if _inside_window(record["scheduled_at"], window_start, window_end)]
    items.extend(windowed_records)
    errors.extend(parse_errors)
    availability.append(
        _availability_record(
            source=source,
            data_class="economic_release",
            status=_availability_status(
                records=records,
                windowed_records=windowed_records,
                errors=parse_errors,
                window_start=window_start,
            ),
            endpoint=BEA_ENDPOINT,
            record_count=len(windowed_records),
            parsed_record_count=len(records),
            error_count=len(parse_errors),
        )
    )
    return {"items": items, "availability": availability, "errors": errors}


def _request_source(
    source_url: str,
    *,
    proxy_url: str | None,
    rate_limit_config_path: Path | None = None,
    rate_limit_source: str | None = None,
) -> str:
    request = Request(source_url, headers={"User-Agent": "Halpha/0.0.0"})
    urlopen_func = urlopen_from_public_proxy(
        proxy_url,
        error_factory=MacroCalendarCollectionError,
        default_urlopen=urlopen,
        proxy_handler_factory=ProxyHandler,
        opener_factory=build_opener,
        rate_limit_config_path=rate_limit_config_path,
        rate_limit_source=rate_limit_source,
    )
    try:
        with urlopen_func(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
    except HTTPError as exc:
        detail = _read_error_detail(exc)
        _record_public_rate_limit_if_needed(
            config_path=rate_limit_config_path,
            url=source_url,
            source=str(rate_limit_source or "macro_calendar"),
            error=exc,
            message=detail,
        )
        raise MacroCalendarCollectionError(f"macro calendar request failed: HTTP {exc.code}{detail}") from exc
    except PublicApiRateLimitError as exc:
        raise MacroCalendarCollectionError(f"macro calendar request rate-limited: {exc}") from exc
    except URLError as exc:
        raise MacroCalendarCollectionError(f"macro calendar request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise MacroCalendarCollectionError("macro calendar request timed out") from exc

    return body.decode("utf-8", errors="replace")


def _parse_federal_reserve_fomc(
    html: str,
    *,
    source: str,
    source_url: str,
    collected_at: str,
    affected_assets: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    parts = [_clean_text(part) for part in parser.parts]
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    current_year: int | None = None
    current_month_label: str | None = None

    for part in parts:
        if not part:
            continue
        year_match = YEAR_HEADING_RE.match(part)
        if year_match:
            current_year = int(year_match.group("year"))
            current_month_label = None
            continue
        if current_year is None:
            continue
        if _is_month_label(part):
            current_month_label = part
            continue
        if current_month_label is None:
            continue
        date_match = DATE_LABEL_RE.match(part)
        if not date_match:
            continue
        try:
            records.append(
                _fomc_record(
                    source=source,
                    source_url=source_url,
                    year=current_year,
                    month_label=current_month_label,
                    date_label=part,
                    start_day=int(date_match.group("start")),
                    end_day=int(date_match.group("end") or date_match.group("start")),
                    has_sep=bool(date_match.group("sep")),
                    collected_at=collected_at,
                    affected_assets=affected_assets,
                )
            )
        except ValueError as exc:
            errors.append(
                {
                    "source": source,
                    "endpoint": FOMC_ENDPOINT,
                    "data_class": "central_bank_event",
                    "error_type": "parse_error",
                    "message": str(exc),
                    "raw_fields": {
                        "year": current_year,
                        "month_label": current_month_label,
                        "date_label": part,
                    },
                }
            )

    if not records and not errors:
        errors.append(
            {
                "source": source,
                "endpoint": FOMC_ENDPOINT,
                "data_class": "central_bank_event",
                "error_type": "parse_error",
                "message": "no FOMC meeting dates were found in source payload",
            }
        )
    return records, errors


def _parse_bea_release_dates(
    body: str,
    *,
    source: str,
    source_url: str,
    collected_at: str,
    affected_assets: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        payload = json.loads(body)
    except JSONDecodeError as exc:
        return [], [
            {
                "source": source,
                "endpoint": BEA_ENDPOINT,
                "data_class": "economic_release",
                "error_type": "parse_error",
                "message": f"BEA release calendar JSON could not be parsed: {exc.msg}",
            }
        ]
    if not isinstance(payload, dict):
        return [], [
            {
                "source": source,
                "endpoint": BEA_ENDPOINT,
                "data_class": "economic_release",
                "error_type": "parse_error",
                "message": "BEA release calendar payload must be a JSON object.",
            }
        ]

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    file_last_updated = _optional_utc_timestamp(payload.get("file_last_updated"))
    for release_name, release_payload in sorted(payload.items()):
        if release_name == "file_last_updated":
            continue
        if not isinstance(release_payload, dict):
            errors.append(_bea_parse_error(source, release_name, "release payload is not a JSON object."))
            continue
        release_dates = release_payload.get("release_dates")
        if not isinstance(release_dates, list):
            errors.append(_bea_parse_error(source, release_name, "release_dates is not a list."))
            continue
        for value in release_dates:
            scheduled_at = _optional_utc_timestamp(value)
            if scheduled_at is None:
                errors.append(_bea_parse_error(source, release_name, f"invalid release date: {value!r}"))
                continue
            key = (release_name, scheduled_at)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                _bea_record(
                    source=source,
                    source_url=source_url,
                    release_name=release_name,
                    scheduled_at=scheduled_at,
                    file_last_updated=file_last_updated,
                    collected_at=collected_at,
                    affected_assets=affected_assets,
                )
            )

    if not records and not errors:
        errors.append(
            {
                "source": source,
                "endpoint": BEA_ENDPOINT,
                "data_class": "economic_release",
                "error_type": "parse_error",
                "message": "no BEA release dates were found in source payload",
            }
        )
    return sorted(records, key=lambda record: (record["scheduled_at"], record["event_name"])), errors


def _bea_record(
    *,
    source: str,
    source_url: str,
    release_name: str,
    scheduled_at: str,
    file_last_updated: str | None,
    collected_at: str,
    affected_assets: list[str],
) -> dict[str, Any]:
    slug = _slug(release_name)
    item_id = f"macro_calendar:economic_release:{source}:US:{slug}:{scheduled_at}"
    return {
        "item_id": item_id,
        "data_class": "economic_release",
        "source": source,
        "event_name": release_name,
        "event_type": "bea_release",
        "region": "US",
        "affected_assets": sorted(set(affected_assets)),
        "scheduled_at": scheduled_at,
        "source_timezone": "UTC",
        "importance": "high" if release_name in BEA_HIGH_IMPORTANCE_RELEASES else "medium",
        "source_published_at": file_last_updated,
        "endpoint": BEA_ENDPOINT,
        "metrics": {},
        "units": {},
        "raw_fields": {
            "source_url": source_url,
            "release_name": release_name,
            "time_precision": "datetime",
        },
        "warnings": [],
        "errors": [],
        "collected_at": collected_at,
    }


def _bea_parse_error(source: str, release_name: str, message: str) -> dict[str, Any]:
    return {
        "source": source,
        "endpoint": BEA_ENDPOINT,
        "data_class": "economic_release",
        "error_type": "parse_error",
        "message": message,
        "raw_fields": {"release_name": release_name},
    }


def _fomc_record(
    *,
    source: str,
    source_url: str,
    year: int,
    month_label: str,
    date_label: str,
    start_day: int,
    end_day: int,
    has_sep: bool,
    collected_at: str,
    affected_assets: list[str],
) -> dict[str, Any]:
    start_month, end_month = _month_range(month_label, start_day=start_day, end_day=end_day)
    event_year = year + 1 if end_month < start_month else year
    scheduled_at = datetime(event_year, end_month, end_day, tzinfo=timezone.utc)
    scheduled_at_text = _utc_timestamp(scheduled_at)
    item_id = f"macro_calendar:central_bank_event:{source}:US:fomc_meeting:{scheduled_at_text}"
    warnings = [DATE_PRECISION_WARNING]
    return {
        "item_id": item_id,
        "data_class": "central_bank_event",
        "source": source,
        "event_name": "Federal Open Market Committee meeting",
        "event_type": "fomc_meeting",
        "region": "US",
        "affected_assets": sorted(set(affected_assets)),
        "scheduled_at": scheduled_at_text,
        "source_timezone": SOURCE_TIMEZONE,
        "importance": "high",
        "source_published_at": None,
        "endpoint": FOMC_ENDPOINT,
        "metrics": {},
        "units": {},
        "raw_fields": {
            "source_url": source_url,
            "year": year,
            "month_label": month_label,
            "date_label": date_label,
            "start_day": start_day,
            "end_day": end_day,
            "summary_of_economic_projections": has_sep,
            "time_precision": "date",
        },
        "warnings": warnings,
        "errors": [],
        "collected_at": collected_at,
    }


def _month_range(month_label: str, *, start_day: int, end_day: int) -> tuple[int, int]:
    labels = [_normalize_month_name(part) for part in month_label.split("/")]
    if not labels:
        raise ValueError(f"unsupported FOMC month label: {month_label}")
    start_month = MONTHS[labels[0]]
    end_month = start_month
    if len(labels) > 1 and end_day < start_day:
        end_month = MONTHS[labels[1]]
    datetime(2024, start_month, start_day)
    datetime(2024, end_month, end_day)
    return start_month, end_month


def _is_month_label(value: str) -> bool:
    try:
        for part in value.split("/"):
            _normalize_month_name(part)
    except ValueError:
        return False
    return True


def _normalize_month_name(value: str) -> str:
    value = value.strip()
    if value in MONTHS:
        return value
    if value in MONTH_ALIASES:
        return MONTH_ALIASES[value]
    raise ValueError(f"unsupported month label: {value}")


def _inside_window(scheduled_at: str, window_start: datetime, window_end: datetime) -> bool:
    value = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    return window_start <= value <= window_end


def _availability_status(
    *,
    records: list[dict[str, Any]],
    windowed_records: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    window_start: datetime,
) -> str:
    if windowed_records and errors:
        return "partial"
    if windowed_records:
        return "succeeded"
    if errors and not records:
        return "failed"
    latest = _latest_scheduled_at(records)
    if latest is not None and latest < window_start:
        return "stale"
    return "no_event"


def _latest_scheduled_at(records: list[dict[str, Any]]) -> datetime | None:
    timestamps = [
        datetime.fromisoformat(str(record["scheduled_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        for record in records
    ]
    return max(timestamps) if timestamps else None


def _raw_artifact(
    source_name: str,
    source_url: str,
    collected_at: str,
    *,
    window_start: str,
    window_end: str,
    sources: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    artifact = {
        "schema_version": 1,
        "artifact_type": "macro_calendar_raw",
        "collector": "macro_calendar",
        "collection_method": "public_http",
        "source": {
            "name": source_name,
            "url": source_url,
        },
        "collected_at": collected_at,
        "window": {
            "lookback_start": window_start,
            "lookahead_end": window_end,
        },
        "items": [],
        "availability": [],
        "warnings": [],
        "errors": [],
    }
    if sources is not None:
        artifact["sources"] = sources
    return artifact


def _availability_record(
    *,
    source: str,
    data_class: str,
    status: str,
    endpoint: str | None = None,
    record_count: int = 0,
    parsed_record_count: int = 0,
    error_count: int = 0,
    reason: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source": source,
        "data_class": data_class,
        "status": status,
        "record_count": record_count,
        "parsed_record_count": parsed_record_count,
        "error_count": error_count,
    }
    if endpoint is not None:
        record["endpoint"] = endpoint
    if reason is not None:
        record["reason"] = reason
    return record


def _manifest_summary(raw: dict[str, Any]) -> dict[str, Any]:
    statuses = sorted(
        {
            str(item.get("status"))
            for item in raw.get("availability", [])
            if isinstance(item, dict) and item.get("status")
        }
    )
    return {
        "status": _artifact_status(raw),
        "artifact": MACRO_CALENDAR_ARTIFACT,
        "item_count": len(raw.get("items", [])),
        "availability_count": len(raw.get("availability", [])),
        "error_count": len(raw.get("errors", [])),
        "availability_statuses": statuses,
    }


def _artifact_status(raw: dict[str, Any]) -> str:
    statuses = {
        str(item.get("status"))
        for item in raw.get("availability", [])
        if isinstance(item, dict) and item.get("status")
    }
    if raw.get("errors") and not raw.get("items"):
        return "failed"
    if "partial" in statuses:
        return "partial"
    if "failed" in statuses:
        return "failed"
    if "stale" in statuses:
        return "stale"
    if "no_event" in statuses:
        return "no_event"
    if raw.get("items"):
        return "succeeded"
    return "warning"


def _record_manifest_counts(
    run: RunContext,
    *,
    items: list[dict[str, Any]],
    availability: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["macro_calendar_items"] = len(items)
    counts["macro_calendar_errors"] = len(errors)
    counts["macro_calendar_availability"] = len(availability)
    counts["macro_calendar_no_event"] = sum(1 for item in availability if item.get("status") == "no_event")
    counts["macro_calendar_stale"] = sum(1 for item in availability if item.get("status") == "stale")
    counts["macro_calendar_unavailable"] = sum(1 for item in availability if item.get("status") == "unavailable")


def _collector_error(*, source: str, message: str, source_url: str) -> dict[str, Any]:
    return {
        "source": source,
        "endpoint": _source_endpoint(source),
        "source_url": source_url,
        "data_class": _source_data_class(source),
        "error_type": "collector_error",
        "message": message,
    }


def _macro_calendar_config(config: dict[str, Any]) -> dict[str, Any]:
    macro_calendar = config.get("macro_calendar")
    return macro_calendar if isinstance(macro_calendar, dict) else {}


def _macro_calendar_sources(macro_calendar: dict[str, Any]) -> list[str]:
    sources = _string_list(macro_calendar.get("sources"))
    if not sources:
        source = str(macro_calendar.get("source") or "").strip()
        sources = [source] if source else [FEDERAL_RESERVE_FOMC_SOURCE]
    return list(dict.fromkeys(sources))


def _macro_calendar_source_urls(macro_calendar: dict[str, Any], sources: list[str]) -> dict[str, str]:
    configured = str(macro_calendar.get("source_url") or "").strip()
    return {
        source: configured if configured and len(sources) == 1 else _default_source_url(source)
        for source in sources
    }


def _default_source_url(source: str) -> str:
    if source == BEA_RELEASE_CALENDAR_SOURCE:
        return BEA_RELEASE_DATES_URL
    return FEDERAL_RESERVE_FOMC_URL


def _source_endpoint(source: str) -> str:
    if source == BEA_RELEASE_CALENDAR_SOURCE:
        return BEA_ENDPOINT
    return FOMC_ENDPOINT


def _source_data_class(source: str) -> str:
    if source == BEA_RELEASE_CALENDAR_SOURCE:
        return "economic_release"
    return "central_bank_event"


def _requested_data_classes_for_source(
    source: str,
    *,
    data_classes: list[str],
    multi_source: bool,
) -> list[str]:
    supported = _source_supported_data_classes(source)
    if not supported:
        return data_classes or ["central_bank_event"]
    requested = data_classes or list(supported)
    selected = [data_class for data_class in requested if data_class in supported]
    if selected or multi_source:
        return selected
    return requested


def _source_supported_data_classes(source: str) -> set[str]:
    if source == FEDERAL_RESERVE_FOMC_SOURCE:
        return {"central_bank_event"}
    if source == BEA_RELEASE_CALENDAR_SOURCE:
        return {"economic_release"}
    return set()


def _market_symbols(config: dict[str, Any]) -> list[str]:
    market = config.get("market")
    if not isinstance(market, dict):
        return []
    return _string_list(market.get("symbols"))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _positive_int(value: Any, *, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _optional_utc_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _utc_timestamp(parsed)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "release"


def _read_error_detail(error: HTTPError) -> str:
    try:
        body = error.read().decode("utf-8").strip()
    except Exception:
        body = ""
    if not body:
        return ""
    excerpt = body[:200].replace("\n", " ")
    return f": {excerpt}"


def _record_public_rate_limit_if_needed(
    *,
    config_path: Path | None,
    url: str,
    source: str,
    error: HTTPError,
    message: str,
) -> None:
    headers = getattr(error, "headers", None)
    if not is_public_api_rate_limit_response(error.code, headers=headers, message=message):
        return
    record_public_api_rate_limit(
        config_path=config_path,
        url=url,
        source=source,
        status_code=error.code,
        retry_after_seconds=retry_after_seconds_from_headers(headers),
        message=message,
    )


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).replace("\xa0", " ").split())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or _utc_now()
    timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


class MacroCalendarCollectionError(Exception):
    pass
