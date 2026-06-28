from __future__ import annotations

import pytest

from halpha.market.instrument_identity import (
    InstrumentIdentityError,
    derive_instrument_identity,
    identity_from_ohlcv_record,
    instrument_identity,
)


def test_derive_instrument_identity_for_binance_spot() -> None:
    identity = derive_instrument_identity(
        source="binance_spot",
        symbol="BTCUSDT",
        timeframe="1d",
    )

    assert identity == {
        "schema_version": 1,
        "source": "binance_spot",
        "symbol": "BTCUSDT",
        "exchange_symbol": "BTC/USDT",
        "market_type": "spot",
        "contract_type": "spot",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "settlement_asset": "none",
        "price_unit": "quote_asset_per_base_asset",
        "timeframe": "1d",
        "identity_status": "normalized",
        "warnings": [],
    }


def test_derive_instrument_identity_for_binance_usdm_swap() -> None:
    identity = derive_instrument_identity(
        source="binance_usdm",
        symbol="BTCUSDT",
        timeframe="1h",
    )

    assert identity["exchange_symbol"] == "BTC/USDT:USDT"
    assert identity["market_type"] == "swap"
    assert identity["contract_type"] == "linear_perpetual"
    assert identity["base_asset"] == "BTC"
    assert identity["quote_asset"] == "USDT"
    assert identity["settlement_asset"] == "USDT"
    assert identity["price_unit"] == "quote_asset_per_base_asset"
    assert identity["identity_status"] == "inferred"
    assert [item["code"] for item in identity["warnings"]] == [
        "contract_terms_inferred_without_market_metadata"
    ]


@pytest.mark.parametrize("source", ["okx_swap", "bybit_swap"])
def test_derive_instrument_identity_for_swap_sources(source: str) -> None:
    identity = derive_instrument_identity(
        source=source,
        symbol="ETHUSDC",
        timeframe="4h",
    )

    assert identity["source"] == source
    assert identity["exchange_symbol"] == "ETH/USDC:USDC"
    assert identity["market_type"] == "swap"
    assert identity["contract_type"] == "linear_perpetual"
    assert identity["base_asset"] == "ETH"
    assert identity["quote_asset"] == "USDC"
    assert identity["settlement_asset"] == "USDC"
    assert identity["identity_status"] == "inferred"


def test_derive_instrument_identity_preserves_exchange_style_symbol() -> None:
    identity = derive_instrument_identity(
        source="okx_swap",
        symbol="BTC/USDT:USDT",
        timeframe="1d",
    )

    assert identity["symbol"] == "BTC/USDT:USDT"
    assert identity["exchange_symbol"] == "BTC/USDT:USDT"
    assert identity["base_asset"] == "BTC"
    assert identity["quote_asset"] == "USDT"
    assert identity["settlement_asset"] == "USDT"


def test_derive_instrument_identity_marks_unknown_symbol_fields() -> None:
    identity = derive_instrument_identity(
        source="binance_usdm",
        symbol="NOT_A_PAIR",
        timeframe="1d",
    )

    assert identity["exchange_symbol"] == "NOT_A_PAIR"
    assert identity["contract_type"] == "unknown"
    assert identity["base_asset"] == "unknown"
    assert identity["quote_asset"] == "unknown"
    assert identity["settlement_asset"] == "unknown"
    assert identity["price_unit"] == "unknown"
    assert identity["identity_status"] == "degraded"
    assert [item["code"] for item in identity["warnings"]] == [
        "symbol_assets_unknown",
        "contract_terms_inferred_without_market_metadata",
    ]


def test_instrument_identity_dataclass_returns_artifact_record() -> None:
    identity = instrument_identity(source="bybit_swap", symbol="SOLUSD", timeframe="1h")

    assert identity.to_record()["contract_type"] == "linear_perpetual"
    assert identity.to_record()["settlement_asset"] == "USD"


def test_identity_from_ohlcv_record_uses_source_symbol_timeframe() -> None:
    identity = identity_from_ohlcv_record(
        {"source": "binance_spot", "symbol": "ETHBTC", "timeframe": "1d"}
    )

    assert identity["exchange_symbol"] == "ETH/BTC"
    assert identity["base_asset"] == "ETH"
    assert identity["quote_asset"] == "BTC"
    assert identity["timeframe"] == "1d"


def test_derive_instrument_identity_rejects_unsupported_source() -> None:
    with pytest.raises(InstrumentIdentityError, match="unsupported OHLCV source"):
        derive_instrument_identity(source="unsupported", symbol="BTCUSDT", timeframe="1d")


def test_derive_instrument_identity_rejects_missing_fields() -> None:
    with pytest.raises(InstrumentIdentityError, match="symbol must be a non-empty string"):
        derive_instrument_identity(source="binance_spot", symbol="", timeframe="1d")
