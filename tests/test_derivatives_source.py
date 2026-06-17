from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from typing import Any
from urllib.error import HTTPError

import pytest

from halpha.derivatives_source import DerivativesSourceError, PublicDerivativesSource


def test_binance_usdm_derivatives_source_parses_supported_payloads() -> None:
    requested_urls: list[str] = []
    payloads = {
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
            "estimatedSettlePrice": "67990.00",
            "lastFundingRate": "0.00038246",
            "interestRate": "0.00010000",
            "nextFundingTime": _millis("2026-06-18T08:00:00Z"),
            "time": _millis("2026-06-18T00:02:00Z"),
        },
        "https://fapi.binance.com/futures/data/basis?pair=BTCUSDT&contractType=PERPETUAL&period=1h&limit=1": [
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
    }

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _FakeResponse(payloads[request.full_url])

    source = PublicDerivativesSource("binance_usdm", urlopen_func=fake_urlopen)

    funding = source.fetch_records("funding_rate_history", symbol="BTCUSDT", limit=2)
    current_oi = source.fetch_records("open_interest_current", symbol="BTCUSDT")
    oi_history = source.fetch_records("open_interest_history", symbol="BTCUSDT", period="1h", limit=2)
    premium = source.fetch_records("premium_index", symbol="BTCUSDT")
    basis = source.fetch_records("basis", symbol="BTCUSDT", period="1h", limit=1)

    assert requested_urls == list(payloads)
    assert funding["errors"] == []
    assert funding["records"][0] == {
        "item_id": "derivatives_market:funding_rate:binance_usdm:BTCUSDT:8h:2026-06-18T00:00:00Z",
        "data_class": "funding_rate",
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": "BTCUSDT",
        "period": "8h",
        "as_of": "2026-06-18T00:00:00Z",
        "endpoint": "funding_rate_history",
        "request_class": "funding_rate_history",
        "metrics": {
            "funding_rate": 0.0001,
            "mark_price": 68000.1,
        },
        "units": {
            "funding_rate": "ratio",
            "mark_price": "quote_asset",
        },
        "raw_fields": {
            "symbol": "BTCUSDT",
            "fundingRate": "0.00010000",
            "fundingTime": _millis("2026-06-18T00:00:00Z"),
            "markPrice": "68000.10",
        },
        "warnings": [],
        "errors": [],
    }
    assert current_oi["records"][0]["metrics"] == {"open_interest_contracts": 10659.509}
    assert current_oi["records"][0]["period"] == "snapshot"
    assert oi_history["records"][0]["metrics"] == {
        "open_interest_contracts": 20403.637,
        "open_interest_value": 150570784.07809979,
        "cmc_circulating_supply": 165880.538,
    }
    assert premium["records"][0]["metrics"]["premium_rate"] == pytest.approx(100.0 / 68000.0)
    assert premium["records"][0]["metrics"]["last_funding_rate"] == 0.00038246
    assert basis["records"][0]["metrics"] == {
        "basis": 13.94054945,
        "basis_rate": 0.0004,
        "futures_price": 34414.1,
        "index_price": 34400.15945055,
    }


def test_derivatives_source_records_partial_malformed_rows() -> None:
    def fake_urlopen(request, timeout):
        return _FakeResponse(
            [
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.00010000",
                    "fundingTime": _millis("2026-06-18T00:00:00Z"),
                },
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "",
                    "fundingTime": _millis("2026-06-18T08:00:00Z"),
                },
            ]
        )

    result = PublicDerivativesSource("binance_usdm", urlopen_func=fake_urlopen).fetch_records(
        "funding_rate_history",
        symbol="BTCUSDT",
    )

    assert len(result["records"]) == 1
    assert result["errors"] == [
        {
            "source": "binance_usdm",
            "market_type": "usd_m_futures",
            "request_class": "funding_rate_history",
            "data_class": "funding_rate",
            "endpoint": "funding_rate_history",
            "symbol": "BTCUSDT",
            "period": "8h",
            "error_type": "malformed_payload",
            "message": "funding_rate_history payload fundingRate must be numeric.",
            "item_path": "row[1]",
        }
    ]


def test_derivatives_source_records_http_unsupported_symbol_error() -> None:
    def fake_urlopen(request, timeout):
        body = b'{"code": -1121, "msg": "Invalid symbol."}'
        raise HTTPError(request.full_url, 400, "Bad Request", None, BytesIO(body))

    result = PublicDerivativesSource("binance_usdm", urlopen_func=fake_urlopen).fetch_records(
        "open_interest_current",
        symbol="BADUSDT",
    )

    assert result["records"] == []
    assert result["errors"] == [
        {
            "source": "binance_usdm",
            "market_type": "usd_m_futures",
            "request_class": "open_interest_current",
            "data_class": "open_interest",
            "endpoint": "open_interest_current",
            "symbol": "BADUSDT",
            "period": "snapshot",
            "error_type": "unsupported_symbol",
            "message": "binance_usdm derivatives endpoint returned HTTP 400: Invalid symbol.",
            "status_code": 400,
            "raw_error_code": -1121,
        }
    ]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"unexpected": "object"}, "funding_rate_history expected a JSON list payload."),
        (b"not-json", "binance_usdm derivatives endpoint returned invalid JSON"),
    ],
)
def test_derivatives_source_records_malformed_endpoint_payload(payload: Any, expected: str) -> None:
    def fake_urlopen(request, timeout):
        if isinstance(payload, bytes):
            return _FakeResponse(raw=payload)
        return _FakeResponse(payload)

    result = PublicDerivativesSource("binance_usdm", urlopen_func=fake_urlopen).fetch_records(
        "funding_rate_history",
        symbol="BTCUSDT",
    )

    assert result["records"] == []
    assert result["errors"][0]["error_type"] == "malformed_payload"
    assert result["errors"][0]["message"] == expected


def test_derivatives_source_rejects_unsupported_source_and_request_class() -> None:
    with pytest.raises(DerivativesSourceError, match="unsupported derivatives source: kraken"):
        PublicDerivativesSource("kraken")

    source = PublicDerivativesSource("binance_usdm", urlopen_func=lambda request, timeout: _FakeResponse({}))
    with pytest.raises(DerivativesSourceError, match="unsupported derivatives request_class"):
        source.fetch_records("liquidation_summary", symbol="BTCUSDT")


def test_derivatives_source_rejects_invalid_request_parameters() -> None:
    source = PublicDerivativesSource("binance_usdm", urlopen_func=lambda request, timeout: _FakeResponse({}))

    with pytest.raises(DerivativesSourceError, match="period must be a non-empty string"):
        source.fetch_records("basis", symbol="BTCUSDT")

    with pytest.raises(DerivativesSourceError, match="does not accept a limit parameter"):
        source.fetch_records("open_interest_current", symbol="BTCUSDT", limit=1)

    with pytest.raises(DerivativesSourceError, match="does not accept a period parameter"):
        source.fetch_records("premium_index", symbol="BTCUSDT", period="1h")


def _millis(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


class _FakeResponse:
    def __init__(self, payload: Any | None = None, *, raw: bytes | None = None) -> None:
        self.payload = payload
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        if self.raw is not None:
            return self.raw
        return json.dumps(self.payload).encode("utf-8")
