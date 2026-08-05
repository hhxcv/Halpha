"""Small Binance account-contract supplement built on Nautilus HTTP clients."""

from __future__ import annotations

import json
from typing import Protocol

from nautilus_trader.core.nautilus_pyo3 import HttpMethod


MULTI_ASSET_MARGIN_PATH = "/fapi/v1/multiAssetsMargin"


class BinanceClock(Protocol):
    def timestamp_ms(self) -> int: ...


class BinanceSignedHttpClient(Protocol):
    async def sign_request(self, **kwargs: object) -> bytes: ...


class BinanceFuturesPositionModeApi(Protocol):
    async def query_futures_hedge_mode(self, **kwargs: object) -> object: ...


class BinanceAccountContractError(RuntimeError):
    """The pinned Nautilus client returned an unusable account-mode response."""


async def query_hedge_mode(
    account_api: BinanceFuturesPositionModeApi,
    *,
    recv_window: str = "5000",
) -> bool:
    """Return Binance dual-side mode using Nautilus' typed account endpoint."""

    response = await account_api.query_futures_hedge_mode(
        recv_window=recv_window
    )
    value = (
        response.get("dualSidePosition")
        if isinstance(response, dict)
        else getattr(response, "dualSidePosition", None)
    )
    if type(value) is not bool:
        raise BinanceAccountContractError(
            "POSITION_MODE_RESPONSE_SCHEMA_MISMATCH"
        )
    return value


async def query_single_asset_mode(
    client: BinanceSignedHttpClient,
    clock: BinanceClock,
    *,
    recv_window: str = "5000",
) -> bool:
    """Read Binance's account-wide asset mode through Nautilus' signed client.

    NautilusTrader 1.230.0 exposes the shared authenticated HTTP client but its
    futures account schema does not expose ``multiAssetsMargin``. Keep this one
    missing read-only endpoint in a single thin adapter instead of introducing a
    second Binance SDK.
    """

    raw = await client.sign_request(
        http_method=HttpMethod.GET,
        url_path=MULTI_ASSET_MARGIN_PATH,
        payload={
            "timestamp": str(clock.timestamp_ms()),
            "recvWindow": recv_window,
        },
        ratelimiter_keys=[
            f"binance:{MULTI_ASSET_MARGIN_PATH}",
            "binance:global",
        ],
    )
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        raise BinanceAccountContractError(
            "MULTI_ASSET_MODE_RESPONSE_NOT_JSON"
        ) from None
    if (
        not isinstance(decoded, dict)
        or type(decoded.get("multiAssetsMargin")) is not bool
    ):
        raise BinanceAccountContractError(
            "MULTI_ASSET_MODE_RESPONSE_SCHEMA_MISMATCH"
        )
    return not decoded["multiAssetsMargin"]
