from __future__ import annotations

import json
import logging
from pathlib import Path

from halpha.logging_utils import configure_local_logging


def test_local_logging_writes_json_lines_and_redacts_private_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    secret = "http://private-proxy.example:7890"
    config = {"market": {"proxy": {"url": secret}}}

    log_path = configure_local_logging(config_path=config_path, config=config)
    logging.getLogger("halpha.test").info(
        "using %s from %s",
        secret,
        config_path,
        extra={"event": "test.logging", "config_path": config_path, "proxy_url": secret},
    )

    content = log_path.read_text(encoding="utf-8")
    payload = json.loads(content.strip().splitlines()[-1])
    assert payload["event"] == "test.logging"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "halpha.test"
    assert "<redacted>" in content
    assert secret not in content
    assert str(tmp_path) not in content
