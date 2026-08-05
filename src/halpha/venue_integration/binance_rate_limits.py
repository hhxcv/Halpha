"""Small fail-closed supplement for Binance Retry-After handling.

Nautilus owns ordinary request throttling.  This module handles the response
contract which cannot be inferred from a local quota: once Binance returns 429
or 418, Halpha must honor the server-provided cooldown before polling again.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import re
from time import time


_RATE_LIMIT_STATUSES = frozenset({418, 429})
_DEFAULT_BACKOFF_SECONDS = {418: 120.0, 429: 60.0}
MAX_BINANCE_RATE_LIMIT_BACKOFF_SECONDS = 3 * 24 * 60 * 60
_BAN_UNTIL_PATTERN = re.compile(
    r"\bIP\s+banned\s+until\s+(?P<timestamp>[0-9]{10,16})\b",
    re.IGNORECASE,
)


def _status_code(exception: BaseException) -> int | None:
    value = getattr(exception, "status", None)
    if value is None:
        value = getattr(exception, "code", None)
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result in _RATE_LIMIT_STATUSES else None


def _retry_after_header(headers: object) -> object | None:
    if headers is None:
        return None
    if isinstance(headers, Mapping):
        for key, value in headers.items():
            normalized = (
                key.decode("ascii", errors="ignore")
                if isinstance(key, bytes)
                else str(key)
            )
            if normalized.casefold() == "retry-after":
                return value
        return None
    getter = getattr(headers, "get", None)
    if callable(getter):
        return getter("Retry-After") or getter("retry-after")
    return None


def _exception_message(exception: BaseException) -> str:
    message = getattr(exception, "message", None)
    if isinstance(message, Mapping):
        message = message.get("msg")
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="ignore")
    if isinstance(message, str):
        return message
    return str(exception)


def _ban_until_retry_seconds(exception: BaseException) -> float | None:
    match = _BAN_UNTIL_PATTERN.search(_exception_message(exception))
    if match is None:
        return None
    raw_timestamp = int(match.group("timestamp"))
    # Binance documents this field as a timestamp and currently emits epoch
    # milliseconds. Accept epoch seconds as well so a representation change
    # cannot turn a real ban into an early retry loop.
    ban_until = (
        raw_timestamp / 1000.0
        if raw_timestamp >= 1_000_000_000_000
        else float(raw_timestamp)
    )
    remaining = ban_until - time()
    if remaining <= 0:
        return None
    # One second avoids retrying on the exact expiry boundary after rounding.
    return min(
        remaining + 1.0,
        float(MAX_BINANCE_RATE_LIMIT_BACKOFF_SECONDS),
    )


def binance_retry_after_seconds(exception: BaseException) -> float | None:
    """Return a bounded Binance cooldown for HTTP 429/418 responses."""

    status = _status_code(exception)
    if status is None:
        return None
    raw = _retry_after_header(getattr(exception, "headers", None))
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="ignore")
    try:
        seconds = Decimal(str(raw).strip())
    except (InvalidOperation, AttributeError, TypeError, ValueError):
        seconds = Decimal("NaN")
    if not seconds.is_finite() or seconds <= 0:
        ban_seconds = _ban_until_retry_seconds(exception)
        if ban_seconds is not None:
            return ban_seconds
        seconds = Decimal(str(_DEFAULT_BACKOFF_SECONDS[status]))
    return float(
        min(seconds, Decimal(MAX_BINANCE_RATE_LIMIT_BACKOFF_SECONDS))
    )
