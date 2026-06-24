from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

from halpha.config import load_config
from halpha.pipeline import PipelineError, run_pipeline


def test_pipeline_collects_binance_market_data_and_writes_raw_artifact(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
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
        stage_handlers={"collect_text_events": _failed_text_stage},
    )

    assert result.succeeded is False
    assert result.failed_stage == "collect_text_events"
    assert requested_urls == [
        "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT"
    ]

    raw = json.loads((result.run.raw_dir / "market.json").read_text(encoding="utf-8"))
    raw_text = json.dumps(raw, ensure_ascii=False).lower()
    assert "manually written" not in raw_text
    assert "manually curated" not in raw_text
    assert raw["schema_version"] == 1
    assert raw["artifact_type"] == "market_raw"
    assert raw["collector"] == "market"
    assert raw["collection_method"] == "public_http"
    assert raw["source"] == {
        "name": "binance",
        "url": "https://data-api.binance.vision",
    }
    assert raw["errors"] == []
    assert raw["items"] == [
        {
            "id": "market:binance:BTCUSDT:2026-06-05T00:30:00Z",
            "symbol": "BTCUSDT",
            "as_of": "2026-06-05T00:30:00Z",
            "metrics": {
                "price": "68000.00",
                "change_24h_pct": "1.25",
                "volume_24h": "123.45",
                "quote_volume_24h": "8394600.00",
            },
            "source": {
                "name": "binance",
                "url": "https://data-api.binance.vision",
            },
        }
    ]

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["raw_market"] == "raw/market.json"
    assert manifest["counts"]["market_items"] == 1
    assert _task(manifest, "collect_market_data")["status"] == "succeeded"
    assert _task(manifest, "collect_market_data")["artifacts"] == ["raw/market.json"]


def test_market_collection_failure_writes_error_artifact_without_fake_records(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def failing_urlopen(request, timeout):
        raise URLError("network unreachable")

    monkeypatch.setattr("halpha.collectors.market.urlopen", failing_urlopen)

    result = run_pipeline(config, config_path=config_path)

    assert result.succeeded is False
    assert result.failed_stage == "collect_market_data"
    assert result.exit_code == 3
    assert "network unreachable" in result.reason

    raw = json.loads((result.run.raw_dir / "market.json").read_text(encoding="utf-8"))
    assert raw["items"] == []
    assert raw["errors"] == [
        {
            "symbol": "BTCUSDT",
            "source": "binance",
            "message": "binance request failed for BTCUSDT: network unreachable",
        }
    ]

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["raw_market"] == "raw/market.json"
    assert manifest["counts"]["market_items"] == 0
    assert manifest["stages"][0]["status"] == "failed"
    assert manifest["stages"][0]["artifacts"] == ["raw/market.json"]
    assert manifest["stages"][0]["error"] == manifest["errors"][0]
    assert "network unreachable" in manifest["errors"][0]["message"]
    assert not (result.run.analysis_dir / "market_material.md").exists()
    assert not (result.run.report_dir / "report.md").exists()


def test_market_collection_uses_configured_proxy(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, proxy_url="http://proxy.example:8080")
    config = load_config(config_path)
    proxy_handlers: list[dict[str, str]] = []
    requested_urls: list[str] = []

    def fake_proxy_handler(proxies):
        proxy_handlers.append(proxies)
        return proxies

    class FakeOpener:
        def open(self, request, timeout):
            requested_urls.append(request.full_url)
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

    def fake_build_opener(handler):
        assert handler == {"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"}
        return FakeOpener()

    monkeypatch.setattr("halpha.collectors.market.ProxyHandler", fake_proxy_handler)
    monkeypatch.setattr("halpha.collectors.market.build_opener", fake_build_opener)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_text_events": _failed_text_stage},
    )

    assert result.succeeded is False
    assert result.failed_stage == "collect_text_events"
    assert proxy_handlers == [{"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"}]
    assert requested_urls == [
        "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT"
    ]


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
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
{proxy_block.rstrip()}
  symbols:
    - BTCUSDT
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: true
  command: codex
  args:
    - exec
    - --sandbox
    - read-only
    - "-"
  timeout_seconds: 300
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _task(manifest: dict, name: str) -> dict:
    return next(
        task
        for stage in manifest["stages"]
        for task in stage.get("tasks", [])
        if task["name"] == name
    )


def _failed_text_stage(config, run) -> None:
    raise PipelineError(
        "stage collect_text_events is not implemented",
        stage="collect_text_events",
        exit_code=3,
    )


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")
