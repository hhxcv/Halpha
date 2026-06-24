from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

from halpha.collectors.onchain_flow import collect_onchain_flow_raw
from halpha.config import load_config
from halpha.pipeline import run_pipeline


def test_pipeline_collects_onchain_flow_raw_artifact(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        if "stablecoincharts" in request.full_url:
            return _FakeResponse(_stablecoin_payload())
        if "n-transactions" in request.full_url:
            return _FakeResponse(_chart_payload("Confirmed Transactions Per Day", "Transactions", [1000, 1200]))
        if "mempool-size" in request.full_url:
            return _FakeResponse(_chart_payload("Mempool Size", "Bytes", [500000, 700000]))
        raise AssertionError(f"unexpected URL: {request.full_url}")

    monkeypatch.setattr("halpha.collectors.onchain_flow.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "halpha.collectors.onchain_flow._utc_now",
        lambda: datetime(2026, 6, 19, tzinfo=timezone.utc),
    )

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="refresh_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    assert len(requested_urls) == 3
    raw = json.loads((result.run.raw_dir / "onchain_flow.json").read_text(encoding="utf-8"))
    assert raw["artifact_type"] == "onchain_flow_raw"
    assert raw["collector"] == "onchain_flow"
    assert raw["collection_method"] == "public_http"
    assert raw["source"]["name"] == "public_aggregate"
    assert raw["errors"] == []
    assert {item["data_class"] for item in raw["items"]} == {
        "chain_activity",
        "network_congestion",
        "stablecoin_supply",
    }
    assert {item["source"] for item in raw["items"]} == {
        "blockchain_com_charts",
        "defillama_stablecoins",
    }
    assert any(item["metrics"].get("total_circulating_usd") == 2500.0 for item in raw["items"])
    assert any(item["metrics"].get("transaction_count") == 1200.0 for item in raw["items"])
    assert any(item["metrics"].get("mempool_size_bytes") == 700000.0 for item in raw["items"])
    assert {item["status"] for item in raw["availability"]} == {"succeeded", "unavailable"}
    exchange_flow = [item for item in raw["availability"] if item["data_class"] == "exchange_flow_availability"][0]
    assert exchange_flow["status"] == "unavailable"
    assert "must not be treated as neutral" in exchange_flow["downstream_implication"]

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["raw_onchain_flow"] == "raw/onchain_flow.json"
    assert manifest["counts"]["onchain_flow_items"] == 6
    assert manifest["counts"]["onchain_flow_errors"] == 0
    assert manifest["counts"]["onchain_flow_unavailable"] == 1
    assert _task(manifest, "collect_onchain_flow_data")["artifacts"] == ["raw/onchain_flow.json"]


def test_disabled_onchain_flow_config_does_not_write_fake_raw_artifact(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, enabled=False)
    config = load_config(config_path)
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _FakeResponse(_stablecoin_payload())

    monkeypatch.setattr("halpha.collectors.onchain_flow.urlopen", fake_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="refresh_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    assert requested_urls == []
    assert not (result.run.raw_dir / "onchain_flow.json").exists()
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert "raw_onchain_flow" not in manifest["artifacts"]
    assert manifest["onchain_flow"]["status"] == "skipped"
    assert manifest["counts"]["onchain_flow_items"] == 0
    assert manifest["counts"]["onchain_flow_errors"] == 0


def test_onchain_flow_records_failed_source_without_fake_items(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, data_classes=["stablecoin_supply"])
    config = load_config(config_path)

    def fake_urlopen(request, timeout):
        raise URLError("network unavailable")

    monkeypatch.setattr("halpha.collectors.onchain_flow.urlopen", fake_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="refresh_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    raw = json.loads((result.run.raw_dir / "onchain_flow.json").read_text(encoding="utf-8"))
    assert raw["items"] == []
    assert raw["availability"][0]["status"] == "failed"
    assert raw["errors"][0]["message"] == "on-chain flow request failed: network unavailable"
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["onchain_flow"]["status"] == "failed"
    assert manifest["counts"]["onchain_flow_errors"] == 1


def test_onchain_flow_records_exchange_flow_unavailable_without_request(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, data_classes=["exchange_flow_availability"])
    config = load_config(config_path)
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _FakeResponse(b"{}")

    monkeypatch.setattr("halpha.collectors.onchain_flow.urlopen", fake_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="refresh_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    assert requested_urls == []
    raw = json.loads((result.run.raw_dir / "onchain_flow.json").read_text(encoding="utf-8"))
    assert raw["items"] == []
    assert raw["availability"] == [
        {
            "source": "public_aggregate",
            "data_class": "exchange_flow_availability",
            "status": "unavailable",
            "record_count": 0,
            "parsed_record_count": 0,
            "error_count": 0,
            "endpoint": "exchange_flow_periodic_public_source",
            "reason": (
                "reliable periodic unauthenticated exchange inflow, outflow, or netflow data is not configured; "
                "missing exchange-flow evidence must not be treated as neutral risk context."
            ),
            "limitations": [
                "reliable exchange netflow is commonly provided by paid or proprietary analytics vendors",
                "public exchange account, deposit, or withdrawal APIs are outside Halpha's product boundary",
                "Halpha does not infer exchange netflow from text or unrelated market metrics",
            ],
            "downstream_implication": (
                "exchange-flow evidence is unavailable and must not be treated as neutral risk context"
            ),
        }
    ]


def test_onchain_flow_uses_configured_public_proxy(monkeypatch) -> None:
    proxy_handlers: list[dict[str, str]] = []
    requested_urls: list[str] = []

    def fake_proxy_handler(proxies: dict[str, str]) -> dict[str, str]:
        proxy_handlers.append(proxies)
        return proxies

    class FakeOpener:
        def open(self, request, timeout):
            requested_urls.append(request.full_url)
            return _FakeResponse(_stablecoin_payload())

    def fake_build_opener(handler):
        assert handler == {"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"}
        return FakeOpener()

    monkeypatch.setattr("halpha.collectors.onchain_flow.ProxyHandler", fake_proxy_handler)
    monkeypatch.setattr("halpha.collectors.onchain_flow.build_opener", fake_build_opener)

    raw = collect_onchain_flow_raw(
        {
            "source": "public_aggregate",
            "data_classes": ["stablecoin_supply"],
            "lookback_days": 7,
        },
        proxy_url=" http://proxy.example:8080 ",
        now=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )

    assert raw["errors"] == []
    assert requested_urls == ["https://stablecoins.llama.fi/stablecoincharts/all"]
    assert proxy_handlers == [{"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"}]


def test_onchain_flow_records_proxy_credentials_error_without_echoing_secret() -> None:
    raw = collect_onchain_flow_raw(
        {
            "source": "public_aggregate",
            "data_classes": ["stablecoin_supply"],
        },
        proxy_url="http://user:password@proxy.example:8080",
        now=datetime(2026, 6, 19, tzinfo=timezone.utc),
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
    data_classes: list[str] | None = None,
) -> Path:
    enabled_value = "true" if enabled else "false"
    data_classes = data_classes or [
        "stablecoin_supply",
        "chain_activity",
        "network_congestion",
        "exchange_flow_availability",
    ]
    data_class_lines = "\n".join(f"    - {item}" for item in data_classes)
    enabled_body = ""
    if enabled:
        enabled_body = f"""
  source: public_aggregate
  data_classes:
{data_class_lines}
  assets:
    - ALL_STABLECOINS
    - BTC
  chains:
    - all
    - bitcoin
  lookback_days: 7
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
macro_calendar:
  enabled: false
onchain_flow:
  enabled: {enabled_value}
{enabled_body.rstrip()}
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


def _stablecoin_payload() -> bytes:
    return json.dumps(
        [
            {
                "date": "1781654400",
                "totalCirculating": {"peggedUSD": 2000},
                "totalCirculatingUSD": {"peggedUSD": 2100},
            },
            {
                "date": "1781740800",
                "totalCirculating": {"peggedUSD": 2400},
                "totalCirculatingUSD": {"peggedUSD": 2500},
            },
        ]
    ).encode("utf-8")


def _chart_payload(name: str, unit: str, values: list[float]) -> bytes:
    return json.dumps(
        {
            "status": "ok",
            "name": name,
            "unit": unit,
            "period": "day",
            "values": [
                {"x": 1781654400 + index * 86400, "y": value}
                for index, value in enumerate(values)
            ],
        }
    ).encode("utf-8")


def _noop_stage(config, run) -> list[str]:
    return []


def _task(manifest: dict, name: str) -> dict:
    return next(
        task
        for stage in manifest["stages"]
        for task in stage.get("tasks", [])
        if task["name"] == name
    )


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload
