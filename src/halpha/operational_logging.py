"""Structured Halpha event logging with deterministic secret redaction."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

import structlog


REDACTED = "[REDACTED]"
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "authorization",
        "cookie",
        "credential_value",
        "csrf_secret",
        "database_password",
        "password",
        "password_hash",
        "private_key",
        "secret",
        "session_secret",
        "smtp_secret",
        "token",
    }
)


def _redact_value(value: Any, secret_values: tuple[str, ...]) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                REDACTED
                if str(key).casefold() in SENSITIVE_KEYS
                else _redact_value(child, secret_values)
            )
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(child, secret_values) for child in value]
    if isinstance(value, str):
        redacted = value
        for secret in secret_values:
            if secret:
                redacted = redacted.replace(secret, REDACTED)
        return redacted
    return value


class SecretRedactor:
    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        self._secret_values = tuple(
            sorted(
                {value for value in secret_values if value},
                key=len,
                reverse=True,
            )
        )

    def __call__(
        self,
        _logger: object,
        _method_name: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        return dict(_redact_value(event_dict, self._secret_values))


def configure_halpha_logging(
    log_directory: Path,
    *,
    role: str,
    secret_values: Iterable[str] = (),
) -> structlog.stdlib.BoundLogger:
    """Configure daily JSONL rotation for the named process role."""

    directory = log_directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        directory / f"{role}.jsonl",
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
        delay=True,
    )
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="observed_at"),
        SecretRedactor(secret_values),
    ]
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(sort_keys=True),
            foreign_pre_chain=shared_processors,
        )
    )
    logger = logging.getLogger(f"halpha.{role}")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
    return structlog.get_logger(f"halpha.{role}").bind(role=role)
