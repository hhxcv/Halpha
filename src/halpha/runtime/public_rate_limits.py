from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from halpha.runtime.state_store import (
    apply_runtime_state_migrations,
    open_runtime_state_connection,
    runtime_state_transaction,
)


PUBLIC_API_RATE_LIMIT_STATE_KEY = "public_api_rate_limits"
RATE_LIMITED_STATUS_CODES = frozenset({418, 429})
DEFAULT_429_COOLDOWN_SECONDS = 60
DEFAULT_418_COOLDOWN_SECONDS = 30 * 60
MAX_STORED_MESSAGE_CHARS = 240
RATE_LIMIT_MESSAGE_RE = re.compile(
    r"\b(rate[-\s]*limit(?:ed)?|too\s+many\s+requests|quota\s+exceeded|request\s+quota|"
    r"throttl(?:ed|ing)|temporarily\s+banned|ip\s+banned|way\s+too\s+many\s+requests)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PublicApiRateLimitError(Exception):
    source: str
    host: str
    cooldown_until: str
    status_code: int | None = None
    retry_after_seconds: int | None = None

    def __str__(self) -> str:
        parts = [f"{self.source} public API is in rate-limit cooldown until {self.cooldown_until}"]
        if self.status_code is not None:
            parts.append(f"HTTP {self.status_code}")
        if self.retry_after_seconds is not None:
            parts.append(f"retry after {self.retry_after_seconds}s")
        return "; ".join(parts)


def active_public_api_cooldown(
    *,
    config_path: Path | None,
    url: str,
    source: str | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any] | None:
    if config_path is None:
        return None
    identity = public_api_identity(url, source=source)
    state = read_public_api_rate_limit_state(config_path=config_path)
    record = state.get("cooldowns", {}).get(identity["key"])
    if not isinstance(record, dict):
        return None
    now_value = _coerce_utc(now)
    cooldown_until = _parse_utc(record.get("cooldown_until"))
    if cooldown_until is None or cooldown_until <= now_value:
        return None
    retry_after_seconds = max(int((cooldown_until - now_value).total_seconds()), 1)
    result = dict(record)
    result["key"] = identity["key"]
    result["host"] = identity["host"]
    result["source"] = record.get("source") or identity["source"]
    result["retry_after_seconds"] = retry_after_seconds
    return result


def raise_if_public_api_rate_limited(
    *,
    config_path: Path | None,
    url: str,
    source: str | None = None,
    now: datetime | str | None = None,
) -> None:
    cooldown = active_public_api_cooldown(config_path=config_path, url=url, source=source, now=now)
    if cooldown is None:
        return
    raise PublicApiRateLimitError(
        source=str(cooldown.get("source") or source or cooldown.get("host") or "public_api"),
        host=str(cooldown.get("host") or ""),
        cooldown_until=str(cooldown["cooldown_until"]),
        status_code=_optional_int(cooldown.get("status_code")),
        retry_after_seconds=_optional_int(cooldown.get("retry_after_seconds")),
    )


def record_public_api_rate_limit(
    *,
    config_path: Path | None,
    url: str,
    source: str | None = None,
    status_code: int | None = None,
    retry_after_seconds: int | None = None,
    message: str | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    if config_path is None:
        return {}
    now_value = _coerce_utc(now)
    identity = public_api_identity(url, source=source)
    cooldown_until = _cooldown_until(
        status_code=status_code,
        retry_after_seconds=retry_after_seconds,
        message=message,
        now=now_value,
    )
    record: dict[str, Any] = {
        "key": identity["key"],
        "host": identity["host"],
        "source": identity["source"],
        "status_code": status_code,
        "cooldown_until": _format_utc(cooldown_until),
        "last_seen_at": _format_utc(now_value),
    }
    seconds = max(int((cooldown_until - now_value).total_seconds()), 1)
    record["retry_after_seconds"] = seconds
    safe_message = sanitize_public_api_error_message(message)
    if safe_message:
        record["reason"] = safe_message

    state = read_public_api_rate_limit_state(config_path=config_path)
    cooldowns = state.setdefault("cooldowns", {})
    existing = cooldowns.get(identity["key"])
    if isinstance(existing, dict):
        existing_until = _parse_utc(existing.get("cooldown_until"))
        if existing_until is not None and existing_until > cooldown_until:
            record["cooldown_until"] = _format_utc(existing_until)
            record["retry_after_seconds"] = max(int((existing_until - now_value).total_seconds()), 1)
    cooldowns[identity["key"]] = record
    state["updated_at"] = _format_utc(now_value)
    write_public_api_rate_limit_state(config_path=config_path, state=state, now=now_value)
    return dict(record)


def read_public_api_rate_limit_state(*, config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return _empty_state()
    try:
        with closing(open_runtime_state_connection(config_path=config_path)) as connection:
            apply_runtime_state_migrations(connection)
            row = connection.execute(
                "SELECT value FROM runtime_state_metadata WHERE key = ?",
                (PUBLIC_API_RATE_LIMIT_STATE_KEY,),
            ).fetchone()
    except sqlite3.Error:
        return _empty_state()
    if row is None:
        return _empty_state()
    try:
        loaded = json.loads(str(row[0]))
    except json.JSONDecodeError:
        return _empty_state()
    if not isinstance(loaded, dict):
        return _empty_state()
    cooldowns = loaded.get("cooldowns")
    if not isinstance(cooldowns, dict):
        loaded["cooldowns"] = {}
    loaded.setdefault("schema_version", 1)
    loaded.setdefault("artifact_type", "public_api_rate_limit_state")
    return loaded


def write_public_api_rate_limit_state(
    *,
    config_path: Path,
    state: dict[str, Any],
    now: datetime | str | None = None,
) -> None:
    now_text = _format_utc(_coerce_utc(now))
    payload = dict(state)
    payload["schema_version"] = 1
    payload["artifact_type"] = "public_api_rate_limit_state"
    payload["updated_at"] = now_text
    payload["cooldowns"] = _active_or_recent_cooldowns(payload.get("cooldowns"), now=_coerce_utc(now))
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with closing(open_runtime_state_connection(config_path=config_path)) as connection:
        apply_runtime_state_migrations(connection, now=now_text)
        with runtime_state_transaction(connection):
            connection.execute(
                """
                INSERT OR REPLACE INTO runtime_state_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (PUBLIC_API_RATE_LIMIT_STATE_KEY, text, now_text),
            )


def public_api_identity(url: str, *, source: str | None = None) -> dict[str, str]:
    parsed = urlparse(str(url))
    host = parsed.netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    if not host:
        host = str(source or "public_api").strip().lower() or "public_api"
    safe_source = str(source or host).strip() or host
    return {"key": host, "host": host, "source": safe_source}


def retry_after_seconds_from_headers(
    headers: Any,
    *,
    now: datetime | str | None = None,
) -> int | None:
    value = headers.get("Retry-After") if headers is not None and hasattr(headers, "get") else None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.isdigit():
        seconds = int(text)
        return seconds if seconds > 0 else None
    try:
        retry_at = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    delta = int((retry_at.astimezone(timezone.utc) - _coerce_utc(now)).total_seconds())
    return max(delta, 1) if delta > 0 else None


def sanitize_public_api_error_message(message: str | None) -> str | None:
    if not isinstance(message, str) or not message.strip():
        return None
    text = " ".join(message.split())
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<redacted-ip>", text)
    text = re.sub(r"https?://[^\s]+", "<redacted-url>", text)
    text = text.replace("localhost", "<redacted-host>")
    return text[:MAX_STORED_MESSAGE_CHARS]


def is_public_api_rate_limit_status(status_code: int | None) -> bool:
    return status_code in RATE_LIMITED_STATUS_CODES


def is_public_api_rate_limit_response(
    status_code: int | None,
    *,
    headers: Any = None,
    message: str | None = None,
) -> bool:
    if is_public_api_rate_limit_status(status_code):
        return True
    if retry_after_seconds_from_headers(headers) is not None:
        return True
    return _message_looks_rate_limited(message)


def _cooldown_until(
    *,
    status_code: int | None,
    retry_after_seconds: int | None,
    message: str | None,
    now: datetime,
) -> datetime:
    banned_until = _binance_banned_until(message)
    if banned_until is not None and banned_until > now:
        return banned_until
    if isinstance(retry_after_seconds, int) and retry_after_seconds > 0:
        return now + timedelta(seconds=retry_after_seconds)
    if status_code == 418:
        return now + timedelta(seconds=DEFAULT_418_COOLDOWN_SECONDS)
    return now + timedelta(seconds=DEFAULT_429_COOLDOWN_SECONDS)


def _binance_banned_until(message: str | None) -> datetime | None:
    if not isinstance(message, str):
        return None
    match = re.search(r"banned\s+until\s+(\d{13})", message, re.IGNORECASE)
    if match is None:
        return None
    timestamp_ms = int(match.group(1))
    return datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc).replace(microsecond=0)


def _message_looks_rate_limited(message: str | None) -> bool:
    if not isinstance(message, str) or not message.strip():
        return False
    return RATE_LIMIT_MESSAGE_RE.search(message) is not None


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "public_api_rate_limit_state",
        "updated_at": None,
        "cooldowns": {},
    }


def _active_or_recent_cooldowns(value: Any, *, now: datetime) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    retained: dict[str, Any] = {}
    stale_before = now - timedelta(days=7)
    for key, record in value.items():
        if not isinstance(record, dict):
            continue
        cooldown_until = _parse_utc(record.get("cooldown_until"))
        last_seen_at = _parse_utc(record.get("last_seen_at"))
        if cooldown_until is not None and cooldown_until >= stale_before:
            retained[str(key)] = record
        elif last_seen_at is not None and last_seen_at >= stale_before:
            retained[str(key)] = record
    return retained


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _coerce_utc(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("public API rate-limit timestamp must include a UTC offset.")
        return value.astimezone(timezone.utc).replace(microsecond=0)
    if isinstance(value, str):
        parsed = _parse_utc(value)
        if parsed is None:
            raise ValueError("public API rate-limit timestamp must be an ISO 8601 string.")
        return parsed
    raise ValueError("public API rate-limit timestamp must be a datetime or ISO 8601 string.")


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _optional_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None
