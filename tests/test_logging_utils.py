from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from halpha.cli import main
from halpha.config import load_config
from halpha.runtime.logging_utils import configure_local_logging
from halpha.pipeline import run_pipeline


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


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


def test_local_logging_uses_cwd_artifact_root_for_subdirectory_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "local.yaml"
    config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")

    log_path = configure_local_logging(config_path=config_path, config={"run": {"output_dir": "runs"}})

    assert log_path == tmp_path / "logs" / "halpha.log"
    assert not (config_dir / "logs").exists()


def test_pipeline_logging_records_stage_lifecycle_without_info_noise(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    log_path = configure_local_logging(config_path=config_path, config=config, level=logging.DEBUG)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_market_data",
        now=datetime(2026, 6, 20, tzinfo=timezone.utc),
        stage_handlers={"collect_market_data": lambda config, run: []},
    )

    assert result.succeeded is True
    events = _log_events(log_path)
    by_event = {event["event"]: event for event in events if "event" in event}
    assert by_event["pipeline.run.start"]["run_id"] == result.run.run_id
    assert by_event["pipeline.stage.start"]["stage"] == "collect_market_data"
    assert by_event["pipeline.stage.start"]["level"] == "DEBUG"
    assert by_event["pipeline.stage.succeeded"]["artifact_count"] == 0
    assert by_event["pipeline.stage.succeeded"]["level"] == "DEBUG"
    assert by_event["pipeline.stages.not_run"]["stage_count"] > 0
    assert by_event["pipeline.run.succeeded"]["run_id"] == result.run.run_id


def test_validate_command_logging_records_failure_without_private_values(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path, proxy_url="http://private-proxy.example:7890")

    exit_code = main(["validate", "--config", str(config_path)])

    assert exit_code == 3
    capsys.readouterr()
    log_path = tmp_path / "logs" / "halpha.log"
    log_text = log_path.read_text(encoding="utf-8")
    events = _log_events(log_path)
    assert "cli.command.start" in {event.get("event") for event in events}
    failed = next(event for event in events if event.get("event") == "cli.command.failed")
    assert failed["command"] == "validate"
    assert failed["stage"] == "product_validation"
    assert failed["exit_code"] == 3
    assert "private-proxy.example" not in log_text
    assert str(config_path) not in log_text
    assert str(tmp_path) not in log_text


def test_market_collector_logging_records_bounded_summary(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_market_config(tmp_path)
    config = load_config(config_path)
    log_path = configure_local_logging(config_path=config_path, config=config)

    def fake_urlopen(request, timeout):
        return _FakeResponse(
            {
                "symbol": "BTCUSDT",
                "lastPrice": "68000.00",
                "priceChangePercent": "1.25",
                "volume": "123.45",
                "quoteVolume": "8394600.00",
                "closeTime": _millis(datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc)),
            }
        )

    monkeypatch.setattr("halpha.collectors.market.urlopen", fake_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_market_data",
        now=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )

    assert result.succeeded is True
    log_text = log_path.read_text(encoding="utf-8")
    events = _log_events(log_path)
    started = next(event for event in events if event.get("event") == "collector.market.start")
    finished = next(event for event in events if event.get("event") == "collector.market.finished")
    assert started["source"] == "binance"
    assert started["symbol_count"] == 1
    assert finished["status"] == "succeeded"
    assert finished["item_count"] == 1
    assert finished["error_count"] == 0
    assert finished["artifact"] == "raw/market.json"
    assert "68000.00" not in log_text
    assert str(config_path) not in log_text
    assert str(tmp_path) not in log_text


def _log_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_config(tmp_path: Path, *, proxy_url: str | None = None) -> Path:
    proxy_block = ""
    if proxy_url is not None:
        proxy_block = f"""
  proxy:
    enabled: true
    url: {proxy_url}
"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: false
{proxy_block.rstrip()}
text:
  enabled: false
  sources: []
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_market_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
text:
  enabled: false
  sources: []
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)
