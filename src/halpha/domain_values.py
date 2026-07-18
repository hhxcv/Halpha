"""Shared immutable value helpers for Halpha domain modules.

The helpers in this module have no database, framework, clock, or venue access.
They exist so identity and Decimal comparisons remain byte-for-byte stable at
every B02 boundary.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
import json
from typing import Any
from uuid import UUID


class DomainValidationError(ValueError):
    """Stable, non-secret domain rejection."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def decimal_from_string(
    value: str,
    *,
    code: str,
    positive: bool = False,
    non_negative: bool = False,
) -> Decimal:
    """Parse an exact finite Decimal without accepting binary floats."""

    if not isinstance(value, str) or not value or value.strip() != value:
        raise DomainValidationError(code)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        raise DomainValidationError(code) from None
    if not parsed.is_finite():
        raise DomainValidationError(code)
    if positive and parsed <= 0:
        raise DomainValidationError(code)
    if non_negative and parsed < 0:
        raise DomainValidationError(code)
    return parsed


def canonical_decimal(value: Decimal) -> str:
    """Render a Decimal without exponent or insignificant trailing zeroes."""

    if not value.is_finite():
        raise DomainValidationError("DECIMAL_NOT_FINITE")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered in {"", "-0"}:
        return "0"
    return rendered


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_json_value(item) for item in value]
        return sorted(items) if isinstance(value, (set, frozenset)) else items
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def content_digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()
