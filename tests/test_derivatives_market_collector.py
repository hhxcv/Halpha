from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

from halpha.config import load_config
from halpha.pipeline import run_pipeline


def test_pipeline_collects_derivatives_market_raw_artifact(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    requested_urls: list[str] = []
    payloads = _successful_payloads()

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _FakeResponse(payloads[request.full_url])

    monkeypatch.setattr("halpha.derivatives_source.urlopen", fake_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_derivatives_market_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    assert requested_urls == list(payloads)
    raw = json.loads((result.run.raw_dir / "derivatives_market.json").read_text(encoding="utf-8"))
    assert raw["artifact_type"] == "derivatives_market_raw"
    assert raw["collector"] == "derivatives_market"
    assert raw["collection_method"] == "public_http"
    assert raw["source"] == {
        "name": "binance_usdm",
        "url": "https://fapi.binance.com",
    }
    assert raw["errors"] == []
    assert len(raw["items"]) == 6
    assert {item["data_class"] for item in raw["items"]} == {
        "basis",
        "funding_rate",
        "open_interest",
        "premium_index",
        "spread_depth",
    }
    assert {item["source"] for item in raw["items"]} == {"binance_usdm"}
    assert {item["market_type"] for item in raw["items"]} == {"usd_m_futures"}
    assert len(raw["availability"]) == 6
    assert {item["status"] for item in raw["availability"]} == {"succeeded"}

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["raw_derivatives_market"] == "raw/derivatives_market.json"
    assert manifest["counts"]["derivatives_market_items"] == 6
    assert manifest["counts"]["derivatives_market_errors"] == 0
    assert manifest["counts"]["derivatives_market_requests"] == 6
    assert manifest["stages"][1]["name"] == "collect_derivatives_market_data"
    assert manifest["stages"][1]["artifacts"] == ["raw/derivatives_market.json"]


def test_pipeline_collects_partial_derivatives_failures_without_fake_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path, data_classes=["funding_rate", "open_interest"])
    config = load_config(config_path)
    payloads = _successful_payloads()

    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/openInterest?symbol=BTCUSDT"):
            body = b'{"code": -1121, "msg": "Invalid symbol."}'
            raise HTTPError(request.full_url, 400, "Bad Request", None, BytesIO(body))
        return _FakeResponse(payloads[request.full_url])

    monkeypatch.setattr("halpha.derivatives_source.urlopen", fake_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_derivatives_market_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    raw = json.loads((result.run.raw_dir / "derivatives_market.json").read_text(encoding="utf-8"))
    assert len(raw["items"]) == 2
    assert raw["errors"] == [
        {
            "source": "binance_usdm",
            "market_type": "usd_m_futures",
            "request_class": "open_interest_current",
            "data_class": "open_interest",
            "endpoint": "open_interest_current",
            "symbol": "BTCUSDT",
            "period": "snapshot",
            "error_type": "unsupported_symbol",
            "message": "binance_usdm derivatives endpoint returned HTTP 400: Invalid symbol.",
            "status_code": 400,
            "raw_error_code": -1121,
        }
    ]
    assert [item["status"] for item in raw["availability"]] == ["succeeded", "failed", "succeeded"]

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["counts"]["derivatives_market_items"] == 2
    assert manifest["counts"]["derivatives_market_errors"] == 1
    assert manifest["counts"]["derivatives_market_requests"] == 3


def test_disabled_derivatives_config_does_not_write_fake_raw_artifact(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, derivatives_enabled=False)
    config = load_config(config_path)
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _FakeResponse({})

    monkeypatch.setattr("halpha.derivatives_source.urlopen", fake_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_derivatives_market_data",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    assert result.succeeded is True
    assert requested_urls == []
    assert not (result.run.raw_dir / "derivatives_market.json").exists()
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert "raw_derivatives_market" not in manifest["artifacts"]
    assert manifest["counts"]["derivatives_market_items"] == 0
    assert manifest["counts"]["derivatives_market_errors"] == 0
    assert manifest["counts"]["derivatives_market_requests"] == 0
    assert manifest["stages"][1]["name"] == "collect_derivatives_market_data"
    assert manifest["stages"][1]["artifacts"] == []


def _write_config(
    tmp_path: Path,
    *,
    derivatives_enabled: bool = True,
    data_classes: list[str] | None = None,
) -> Path:
    data_classes = data_classes or ["funding_rate", "open_interest", "premium_index", "basis", "spread_depth"]
    data_class_lines = "\n".join(f"      - {data_class}" for data_class in data_classes)
    enabled_value = "true" if derivatives_enabled else "false"
    extra_derivatives = ""
    if derivatives_enabled:
        extra_derivatives = f"""
    source: binance_usdm
    symbols:
      - BTCUSDT
    data_classes:
{data_class_lines}
    periods:
      - 1h
    lookback:
      1h: 2
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
  derivatives:
    enabled: {enabled_value}
{extra_derivatives.rstrip()}
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


def _successful_payloads() -> dict[str, object]:
    return {
        "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=2": [
            {
                "symbol": "BTCUSDT",
                "fundingRate": "0.00010000",
                "fundingTime": _millis("2026-06-18T00:00:00Z"),
                "markPrice": "68000.10",
            }
        ],
        "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT": {
            "symbol": "BTCUSDT",
            "openInterest": "10659.509",
            "time": _millis("2026-06-18T00:01:00Z"),
        },
        "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1h&limit=2": [
            {
                "symbol": "BTCUSDT",
                "sumOpenInterest": "20403.63700000",
                "sumOpenInterestValue": "150570784.07809979",
                "CMCCirculatingSupply": "165880.538",
                "timestamp": str(_millis("2026-06-18T00:00:00Z")),
            }
        ],
        "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT": {
            "symbol": "BTCUSDT",
            "markPrice": "68100.00",
            "indexPrice": "68000.00",
            "lastFundingRate": "0.00038246",
            "interestRate": "0.00010000",
            "time": _millis("2026-06-18T00:02:00Z"),
        },
        "https://fapi.binance.com/futures/data/basis?pair=BTCUSDT&contractType=PERPETUAL&period=1h&limit=2": [
            {
                "indexPrice": "34400.15945055",
                "contractType": "PERPETUAL",
                "basisRate": "0.0004",
                "futuresPrice": "34414.10",
                "annualizedBasisRate": "",
                "basis": "13.94054945",
                "pair": "BTCUSDT",
                "timestamp": _millis("2026-06-18T00:00:00Z"),
            }
        ],
        "https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=20": {
            "lastUpdateId": 1027024,
            "E": _millis("2026-06-18T00:03:01Z"),
            "T": _millis("2026-06-18T00:03:00Z"),
            "bids": [["100.00", "2.0"], ["99.90", "3.0"]],
            "asks": [["100.05", "1.0"], ["100.10", "2.0"]],
        },
    }


def _millis(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _noop_stage(config, run) -> list[str]:
    return []


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")
