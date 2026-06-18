from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from halpha.pipeline import RunContext
from halpha.raw_artifacts import RawArtifactError, validate_macro_calendar_raw_artifact
from halpha.storage import write_json


STAGE_NAME = "collect_macro_calendar_data"
MACRO_CALENDAR_ARTIFACT = "raw/macro_calendar.json"
FEDERAL_RESERVE_FOMC_SOURCE = "federal_reserve_fomc"
FEDERAL_RESERVE_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
REQUEST_TIMEOUT_SECONDS = 20
SOURCE_TIMEZONE = "America/New_York"
FOMC_ENDPOINT = "fomc_calendars"
DATE_PRECISION_WARNING = (
    "source provides FOMC meeting dates without exact intraday time; "
    "scheduled_at is normalized to the meeting end date at 00:00:00Z."
)

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
        proxy_url=_proxy_url_from_market_config(config),
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
) -> dict[str, Any]:
    now_value = _utc_now() if now is None else now.astimezone(timezone.utc)
    collected_at = _utc_timestamp(now_value)
    source = str(macro_calendar.get("source") or "")
    source_url = str(macro_calendar.get("source_url") or FEDERAL_RESERVE_FOMC_URL)
    lookback_days = _positive_int(macro_calendar.get("lookback_days"), default=7)
    lookahead_days = _positive_int(macro_calendar.get("lookahead_days"), default=45)
    window_start = now_value - timedelta(days=lookback_days)
    window_end = now_value + timedelta(days=lookahead_days)
    data_classes = _string_list(macro_calendar.get("data_classes"))
    raw = _raw_artifact(
        source,
        source_url,
        collected_at,
        window_start=_utc_timestamp(window_start),
        window_end=_utc_timestamp(window_end),
    )

    if source != FEDERAL_RESERVE_FOMC_SOURCE:
        raw["availability"].append(
            _availability_record(
                source=source,
                data_class="central_bank_event",
                status="unavailable",
                reason=f"{source} macro/calendar collection is not implemented.",
            )
        )
        validate_macro_calendar_raw_artifact(raw, MACRO_CALENDAR_ARTIFACT)
        return raw

    if "central_bank_event" not in data_classes:
        raw["availability"].append(
            _availability_record(
                source=source,
                data_class="central_bank_event",
                status="skipped",
                reason="central_bank_event is not configured.",
            )
        )
        validate_macro_calendar_raw_artifact(raw, MACRO_CALENDAR_ARTIFACT)
        return raw

    try:
        body = _request_source(source_url, proxy_url=proxy_url)
    except MacroCalendarCollectionError as exc:
        error = _collector_error(source=source, message=str(exc), source_url=source_url)
        raw["errors"].append(error)
        raw["availability"].append(
            _availability_record(
                source=source,
                data_class="central_bank_event",
                status="failed",
                endpoint=FOMC_ENDPOINT,
                error_count=1,
                reason=str(exc),
            )
        )
    else:
        records, errors = _parse_federal_reserve_fomc(
            body,
            source=source,
            source_url=source_url,
            collected_at=collected_at,
            affected_assets=affected_assets or [],
        )
        windowed_records = [
            record for record in records if _inside_window(record["scheduled_at"], window_start, window_end)
        ]
        raw["items"].extend(windowed_records)
        raw["errors"].extend(errors)
        raw["availability"].append(
            _availability_record(
                source=source,
                data_class="central_bank_event",
                status=_availability_status(
                    records=records,
                    windowed_records=windowed_records,
                    errors=errors,
                    window_start=window_start,
                ),
                endpoint=FOMC_ENDPOINT,
                record_count=len(windowed_records),
                parsed_record_count=len(records),
                error_count=len(errors),
            )
        )

    try:
        validate_macro_calendar_raw_artifact(raw, MACRO_CALENDAR_ARTIFACT)
    except RawArtifactError as exc:
        raw["errors"].append(_collector_error(source=source, message=str(exc), source_url=source_url))
    return raw


def _request_source(source_url: str, *, proxy_url: str | None) -> str:
    request = Request(source_url, headers={"User-Agent": "Halpha/0.0.0"})
    urlopen_func = _urlopen_from_proxy(proxy_url)
    try:
        with urlopen_func(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
    except HTTPError as exc:
        detail = _read_error_detail(exc)
        raise MacroCalendarCollectionError(f"macro calendar request failed: HTTP {exc.code}{detail}") from exc
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
) -> dict[str, Any]:
    return {
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
        "endpoint": FOMC_ENDPOINT,
        "source_url": source_url,
        "data_class": "central_bank_event",
        "error_type": "collector_error",
        "message": message,
    }


def _macro_calendar_config(config: dict[str, Any]) -> dict[str, Any]:
    macro_calendar = config.get("macro_calendar")
    return macro_calendar if isinstance(macro_calendar, dict) else {}


def _market_symbols(config: dict[str, Any]) -> list[str]:
    market = config.get("market")
    if not isinstance(market, dict):
        return []
    return _string_list(market.get("symbols"))


def _proxy_url_from_market_config(config: dict[str, Any]) -> str | None:
    market = config.get("market")
    if not isinstance(market, dict):
        return None
    proxy = market.get("proxy")
    if not isinstance(proxy, dict) or proxy.get("enabled") is not True:
        return None
    value = proxy.get("url")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _urlopen_from_proxy(proxy_url: str | None):
    proxy_url = _normalize_proxy_url(proxy_url)
    if proxy_url is None:
        return urlopen
    opener = build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url}))
    return opener.open


def _normalize_proxy_url(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise MacroCalendarCollectionError("market.proxy.url must be a non-empty string.")
    proxy_url = value.strip()
    parsed = urlparse(proxy_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MacroCalendarCollectionError("market.proxy.url must be an http or https URL.")
    if parsed.username or parsed.password:
        raise MacroCalendarCollectionError("market.proxy.url must not include credentials.")
    return proxy_url


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _positive_int(value: Any, *, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _read_error_detail(error: HTTPError) -> str:
    try:
        body = error.read().decode("utf-8").strip()
    except Exception:
        body = ""
    if not body:
        return ""
    excerpt = body[:200].replace("\n", " ")
    return f": {excerpt}"


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
