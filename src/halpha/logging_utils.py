from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .storage import config_base


LOG_ARTIFACT = "logs/halpha.log"
MAX_LOG_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3
PRIVATE_KEY_PARTS = (
    "account",
    "cookie",
    "credential",
    "endpoint",
    "host",
    "password",
    "path",
    "port",
    "proxy",
    "secret",
    "token",
    "url",
    "user",
)
_HALPHA_HANDLER_MARKER = "_halpha_local_file_handler"
_LOG_RECORD_RESERVED = set(logging.makeLogRecord({}).__dict__)


def configure_local_logging(
    *,
    config_path: Path,
    config: dict[str, Any] | None = None,
    level: int = logging.INFO,
) -> Path:
    base = config_base(config_path)
    log_path = base / LOG_ARTIFACT
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("halpha")
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        if getattr(handler, _HALPHA_HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    setattr(handler, _HALPHA_HANDLER_MARKER, True)
    handler.setLevel(level)
    handler.setFormatter(_JsonLogFormatter(_private_values(config_path=config_path, config=config)))
    logger.addHandler(handler)
    return log_path


def redact_private_text(text: str, *, config_path: Path, config: dict[str, Any] | None = None) -> str:
    output = text
    for private in sorted(_private_values(config_path=config_path, config=config), key=len, reverse=True):
        if private:
            output = output.replace(private, "<redacted>")
    return output


class _JsonLogFormatter(logging.Formatter):
    def __init__(self, private_values: set[str]) -> None:
        super().__init__()
        self.private_values = sorted((value for value in private_values if value), key=len, reverse=True)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": self._sanitize(record.getMessage()),
        }
        for key, value in sorted(record.__dict__.items()):
            if key in _LOG_RECORD_RESERVED or key.startswith("_"):
                continue
            payload[key] = self._sanitize(value)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._sanitize_text(value)
        if isinstance(value, Path):
            return self._sanitize_text(value.as_posix())
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [self._sanitize(item) for item in value[:50]]
        if isinstance(value, tuple):
            return [self._sanitize(item) for item in value[:50]]
        if isinstance(value, dict):
            return {str(key): self._sanitize(item) for key, item in sorted(value.items())}
        return self._sanitize_text(str(value))

    def _sanitize_text(self, text: str) -> str:
        return _redact_values(text, self.private_values)


def _private_values(*, config_path: Path, config: dict[str, Any] | None) -> set[str]:
    values: set[str] = set()
    path = Path(config_path)
    candidates = [path, path.parent]
    with_resolved = []
    for candidate in candidates:
        try:
            with_resolved.append(candidate.resolve())
        except OSError:
            pass
    for candidate in [*candidates, *with_resolved]:
        if str(candidate) not in {"", "."}:
            values.add(str(candidate))
            values.add(candidate.as_posix())
    if config:
        _collect_private_config_values(config, (), values)
    return values


def _collect_private_config_values(value: Any, key_path: tuple[str, ...], output: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _collect_private_config_values(item, (*key_path, str(key)), output)
        return
    if isinstance(value, list):
        for item in value:
            _collect_private_config_values(item, key_path, output)
        return
    if not isinstance(value, str) or not value:
        return
    if any(_is_private_key(key) for key in key_path):
        output.add(value)


def _is_private_key(key: str) -> bool:
    lowered = key.lower()
    if lowered == "report":
        return False
    return any(part in lowered for part in PRIVATE_KEY_PARTS)


def _redact_values(text: str, private_values: list[str]) -> str:
    output = text
    for private in private_values:
        output = output.replace(private, "<redacted>")
    return output
