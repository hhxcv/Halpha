from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.market.instrument_identity import InstrumentIdentityError, derive_instrument_identity
from halpha.quant.funding_costs import build_funding_cost_input


CONTRACT_MARKET_TYPES = {"perpetual", "swap", "futures"}
CONTRACT_TYPES = {"linear_perpetual", "inverse_perpetual", "linear_futures", "inverse_futures"}


def funding_cost_input_for_strategy(
    config_path: Path,
    *,
    market_identity: dict[str, Any],
    ohlcv_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    identity = _contract_identity(market_identity)
    if identity is None:
        return None
    return build_funding_cost_input(
        config_path,
        market_identity={**market_identity, **identity},
        ohlcv_rows=ohlcv_rows,
    )


def _contract_identity(market_identity: dict[str, Any]) -> dict[str, Any] | None:
    nested = market_identity.get("instrument_identity")
    if isinstance(nested, dict):
        return nested if _is_contract_identity(nested) else None

    if any(key in market_identity for key in ("market_type", "contract_type", "settlement_asset")):
        return market_identity if _is_contract_identity(market_identity) else None

    source = market_identity.get("source")
    symbol = market_identity.get("symbol")
    timeframe = market_identity.get("timeframe")
    if not all(isinstance(value, str) and value.strip() for value in (source, symbol, timeframe)):
        return None
    try:
        identity = derive_instrument_identity(source=source, symbol=symbol, timeframe=timeframe)
    except InstrumentIdentityError:
        return None
    return identity if _is_contract_identity(identity) else None


def _is_contract_identity(identity: dict[str, Any]) -> bool:
    market_type = str(identity.get("market_type") or "").strip().lower()
    contract_type = str(identity.get("contract_type") or "").strip().lower()
    return market_type in CONTRACT_MARKET_TYPES or contract_type in CONTRACT_TYPES
