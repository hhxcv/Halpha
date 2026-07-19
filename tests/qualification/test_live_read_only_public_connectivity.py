from __future__ import annotations

import json

from tools.qualification.probe_live_read_only_public_connectivity import (
    EXCHANGE_INFO_URL,
    TIME_URL,
    probe_public_endpoints,
)


class _Response:
    def __init__(self, status: int, payload: dict[str, object]) -> None:
        self.status = status
        self._payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class _Opener:
    def open(self, request, *, timeout: int):
        assert request.get_method() == "GET"
        assert timeout == 20
        if request.full_url == TIME_URL:
            return _Response(200, {"serverTime": 1})
        assert request.full_url == EXCHANGE_INFO_URL
        return _Response(
            200,
            {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "contractType": "PERPETUAL",
                        "status": "TRADING",
                    }
                ]
            },
        )


def test_public_connectivity_transport_returns_only_sanitized_observations() -> None:
    observations = probe_public_endpoints(
        proxy_url="sensitive-proxy-value",
        opener_builder=lambda _handler: _Opener(),
    )

    assert observations == {
        "time_http_status": 200,
        "exchange_info_http_status": 200,
        "server_time_integer": True,
        "btcusdt_symbol_present": True,
        "btcusdt_contract_type": "PERPETUAL",
        "btcusdt_status": "TRADING",
    }
    assert "proxy" not in observations
