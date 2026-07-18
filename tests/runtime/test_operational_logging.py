from __future__ import annotations

import json
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from halpha.operational_logging import REDACTED, configure_halpha_logging


def test_jsonl_logging_redacts_named_and_embedded_secrets(tmp_path: Path) -> None:
    secret = "private-value-123"
    logger = configure_halpha_logging(tmp_path, role="test", secret_values=(secret,))
    logger.info(
        "qualification_event",
        password="named-password",
        nested={"authorization": "Bearer material", "safe": f"prefix-{secret}-suffix"},
        credential_reference="Halpha/Binance/BINANCE_DEMO:api_key",
    )
    rendered = (tmp_path / "test.jsonl").read_text(encoding="utf-8")
    assert secret not in rendered
    assert "named-password" not in rendered
    payload = json.loads(rendered)
    assert payload["password"] == REDACTED
    assert payload["nested"]["authorization"] == REDACTED
    assert payload["nested"]["safe"] == f"prefix-{REDACTED}-suffix"
    assert payload["credential_reference"].startswith("Halpha/")


def test_logger_uses_daily_rotation_and_fourteen_day_retention(tmp_path: Path) -> None:
    logger = configure_halpha_logging(tmp_path, role="rotation")
    handlers = logger._logger.handlers
    assert len(handlers) == 1
    handler = handlers[0]
    assert isinstance(handler, TimedRotatingFileHandler)
    assert handler.backupCount == 14
    assert handler.when == "MIDNIGHT"
