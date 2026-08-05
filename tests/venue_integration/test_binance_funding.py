from datetime import UTC, datetime
import asyncio
import json

import pytest
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from halpha.venue_integration.binance_funding import (
    BinanceFundingContractError,
    query_funding_income,
)


NOW = datetime(2026, 7, 26, tzinfo=UTC)


class _Clock:
    @staticmethod
    def timestamp_ms() -> int:
        return int(NOW.timestamp() * 1000)


class _Client:
    def __init__(self, pages: list[object]) -> None:
        self.pages = pages
        self.calls: list[dict[str, object]] = []

    async def sign_request(self, **kwargs: object) -> bytes:
        self.calls.append(kwargs)
        return json.dumps(self.pages.pop(0)).encode()


def test_funding_query_reuses_signed_get_and_preserves_decimal_text() -> None:
    client = _Client(
        [
            [
                {
                    "symbol": "BTCUSDT",
                    "incomeType": "FUNDING_FEE",
                    "income": "-0.00000005",
                    "asset": "USDT",
                    "time": int(NOW.timestamp() * 1000),
                    "tranId": 123,
                }
            ]
        ]
    )

    records = asyncio.run(
        query_funding_income(
            client,
            _Clock(),
            symbol="BTCUSDT",
            start_time=NOW,
            end_time=NOW,
        )
    )

    assert records[0].income == "-0.00000005"
    assert records[0].transaction_id == "123"
    assert client.calls[0]["http_method"] is HttpMethod.GET
    assert client.calls[0]["url_path"] == "/fapi/v1/income"


def test_funding_query_rejects_wrong_symbol_or_identity_conflict() -> None:
    wrong_symbol = _Client(
        [
            [
                {
                    "symbol": "ETHUSDT",
                    "incomeType": "FUNDING_FEE",
                    "income": "1",
                    "asset": "USDT",
                    "time": int(NOW.timestamp() * 1000),
                    "tranId": 1,
                }
            ]
        ]
    )
    with pytest.raises(
        BinanceFundingContractError,
        match="FUNDING_INCOME_RESPONSE_SCHEMA_MISMATCH",
    ):
        asyncio.run(
            query_funding_income(
                wrong_symbol,
                _Clock(),
                symbol="BTCUSDT",
                start_time=NOW,
                end_time=NOW,
            )
        )
