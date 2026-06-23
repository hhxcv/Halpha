from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

from halpha.collectors.macro_calendar import collect_macro_calendar_raw
from halpha.config import load_config
from halpha.pipeline import run_pipeline


def test_pipeline_collects_macro_calendar_raw_artifact(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _FakeResponse(_fomc_html())

    monkeypatch.setattr("halpha.collectors.macro_calendar.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "halpha.collectors.macro_calendar._utc_now",
        lambda: datetime(2026, 6, 18, tzinfo=timezone.utc),
    )

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_macro_calendar_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    assert requested_urls == ["https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"]
    raw = json.loads((result.run.raw_dir / "macro_calendar.json").read_text(encoding="utf-8"))
    assert raw["artifact_type"] == "macro_calendar_raw"
    assert raw["collector"] == "macro_calendar"
    assert raw["collection_method"] == "public_http"
    assert raw["source"] == {
        "name": "federal_reserve_fomc",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    }
    assert raw["errors"] == []
    assert [item["scheduled_at"] for item in raw["items"]] == [
        "2026-06-17T00:00:00Z",
        "2026-07-29T00:00:00Z",
    ]
    assert {item["data_class"] for item in raw["items"]} == {"central_bank_event"}
    assert {item["source_timezone"] for item in raw["items"]} == {"America/New_York"}
    assert {item["importance"] for item in raw["items"]} == {"high"}
    assert all("without exact intraday time" in item["warnings"][0] for item in raw["items"])
    assert raw["availability"] == [
        {
            "source": "federal_reserve_fomc",
            "data_class": "central_bank_event",
            "status": "succeeded",
            "record_count": 2,
            "parsed_record_count": 2,
            "error_count": 0,
            "endpoint": "fomc_calendars",
        }
    ]

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["raw_macro_calendar"] == "raw/macro_calendar.json"
    assert manifest["counts"]["macro_calendar_items"] == 2
    assert manifest["counts"]["macro_calendar_errors"] == 0
    assert manifest["macro_calendar"]["status"] == "succeeded"
    assert manifest["stages"][5]["name"] == "collect_macro_calendar_data"
    assert manifest["stages"][5]["artifacts"] == ["raw/macro_calendar.json"]


def test_disabled_macro_calendar_config_does_not_write_fake_raw_artifact(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, enabled=False)
    config = load_config(config_path)
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _FakeResponse(_fomc_html())

    monkeypatch.setattr("halpha.collectors.macro_calendar.urlopen", fake_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_macro_calendar_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    assert requested_urls == []
    assert not (result.run.raw_dir / "macro_calendar.json").exists()
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert "raw_macro_calendar" not in manifest["artifacts"]
    assert manifest["macro_calendar"]["status"] == "skipped"
    assert manifest["counts"]["macro_calendar_items"] == 0
    assert manifest["counts"]["macro_calendar_errors"] == 0


def test_unconfigured_macro_calendar_records_skipped_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_macro_calendar=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_macro_calendar_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    assert not (result.run.raw_dir / "macro_calendar.json").exists()
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["macro_calendar"]["status"] == "skipped"
    assert manifest["stages"][5]["artifacts"] == []


def test_macro_calendar_records_failed_source_without_fake_items(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fake_urlopen(request, timeout):
        raise URLError("network unavailable")

    monkeypatch.setattr("halpha.collectors.macro_calendar.urlopen", fake_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_macro_calendar_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    raw = json.loads((result.run.raw_dir / "macro_calendar.json").read_text(encoding="utf-8"))
    assert raw["items"] == []
    assert raw["availability"][0]["status"] == "failed"
    assert raw["errors"][0]["message"] == "macro calendar request failed: network unavailable"
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["macro_calendar"]["status"] == "failed"
    assert manifest["counts"]["macro_calendar_errors"] == 1


def test_macro_calendar_records_partial_parse_without_dropping_valid_items(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path, lookback_days=1, lookahead_days=30)
    config = load_config(config_path)

    def fake_urlopen(request, timeout):
        return _FakeResponse(
            """
            <html><body>
              <h4>2026 FOMC Meetings</h4>
              <p>February</p><p>30-31</p>
              <p>March</p><p>17-18</p>
            </body></html>
            """.encode("utf-8")
        )

    monkeypatch.setattr("halpha.collectors.macro_calendar.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "halpha.collectors.macro_calendar._utc_now",
        lambda: datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_macro_calendar_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    raw = json.loads((result.run.raw_dir / "macro_calendar.json").read_text(encoding="utf-8"))
    assert [item["scheduled_at"] for item in raw["items"]] == ["2026-03-18T00:00:00Z"]
    assert raw["availability"][0]["status"] == "partial"
    assert raw["errors"][0]["error_type"] == "parse_error"


def test_macro_calendar_records_no_event_window(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, lookback_days=1, lookahead_days=7)
    config = load_config(config_path)

    monkeypatch.setattr("halpha.collectors.macro_calendar.urlopen", lambda request, timeout: _FakeResponse(_fomc_html()))
    monkeypatch.setattr(
        "halpha.collectors.macro_calendar._utc_now",
        lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_macro_calendar_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    raw = json.loads((result.run.raw_dir / "macro_calendar.json").read_text(encoding="utf-8"))
    assert raw["items"] == []
    assert raw["availability"][0]["status"] == "no_event"
    assert raw["errors"] == []


def test_macro_calendar_records_stale_calendar(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, lookback_days=7, lookahead_days=45)
    config = load_config(config_path)

    def fake_urlopen(request, timeout):
        return _FakeResponse(
            """
            <html><body>
              <h4>2025 FOMC Meetings</h4>
              <p>January</p><p>28-29</p>
            </body></html>
            """.encode("utf-8")
        )

    monkeypatch.setattr("halpha.collectors.macro_calendar.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "halpha.collectors.macro_calendar._utc_now",
        lambda: datetime(2026, 6, 18, tzinfo=timezone.utc),
    )

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_macro_calendar_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    raw = json.loads((result.run.raw_dir / "macro_calendar.json").read_text(encoding="utf-8"))
    assert raw["items"] == []
    assert raw["availability"][0]["status"] == "stale"
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["counts"]["macro_calendar_stale"] == 1


def test_macro_calendar_uses_configured_public_proxy(monkeypatch) -> None:
    proxy_handlers: list[dict[str, str]] = []
    requested_urls: list[str] = []

    def fake_proxy_handler(proxies: dict[str, str]) -> dict[str, str]:
        proxy_handlers.append(proxies)
        return proxies

    class FakeOpener:
        def open(self, request, timeout):
            requested_urls.append(request.full_url)
            return _FakeResponse(_fomc_html())

    def fake_build_opener(handler):
        assert handler == {"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"}
        return FakeOpener()

    monkeypatch.setattr("halpha.collectors.macro_calendar.ProxyHandler", fake_proxy_handler)
    monkeypatch.setattr("halpha.collectors.macro_calendar.build_opener", fake_build_opener)

    raw = collect_macro_calendar_raw(
        {
            "source": "federal_reserve_fomc",
            "data_classes": ["central_bank_event"],
            "lookback_days": 7,
            "lookahead_days": 45,
        },
        proxy_url=" http://proxy.example:8080 ",
        now=datetime(2026, 6, 18, tzinfo=timezone.utc),
    )

    assert raw["errors"] == []
    assert requested_urls == ["https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"]
    assert proxy_handlers == [{"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"}]


def test_macro_calendar_records_proxy_credentials_error_without_echoing_secret() -> None:
    raw = collect_macro_calendar_raw(
        {
            "source": "federal_reserve_fomc",
            "data_classes": ["central_bank_event"],
        },
        proxy_url="http://user:password@proxy.example:8080",
        now=datetime(2026, 6, 18, tzinfo=timezone.utc),
    )

    message = raw["errors"][0]["message"]
    assert message == "market.proxy.url must not include credentials."
    assert raw["availability"][0]["status"] == "failed"
    assert "user" not in message
    assert "password" not in message
    assert "proxy.example" not in message


def _write_config(
    tmp_path: Path,
    *,
    enabled: bool = True,
    include_macro_calendar: bool = True,
    lookback_days: int = 7,
    lookahead_days: int = 45,
) -> Path:
    enabled_value = "true" if enabled else "false"
    macro_calendar_block = ""
    if include_macro_calendar:
        macro_calendar_block = f"""
macro_calendar:
  enabled: {enabled_value}
"""
        if enabled:
            macro_calendar_block += f"""
  source: federal_reserve_fomc
  data_classes:
    - central_bank_event
  regions:
    - US
  lookback_days: {lookback_days}
  lookahead_days: {lookahead_days}
"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
    - ETHUSDT
{macro_calendar_block.rstrip()}
text:
  enabled: false
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _fomc_html() -> bytes:
    return b"""
<html><body>
  <h4>2026 FOMC Meetings</h4>
  <p>June</p><p>16-17*</p>
  <p>July</p><p>28-29</p>
</body></html>
"""


def _noop_stage(config, run) -> list[str]:
    return []


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload
