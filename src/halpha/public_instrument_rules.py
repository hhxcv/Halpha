"""On-demand, short-lived public instrument rules for order-schedule preview."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import re
from time import monotonic
from typing import Protocol

from nautilus_trader.adapters.binance import get_cached_binance_http_client
from nautilus_trader.adapters.binance.common.enums import (
    BinanceAccountType,
    BinanceEnvironment,
)
from nautilus_trader.adapters.binance.futures.http.market import (
    BinanceFuturesMarketHttpAPI,
)
from nautilus_trader.common.component import LiveClock

from halpha.planning.order_schedule import InstrumentOrderRules
from halpha.venue_integration.binance_rules import (
    BinanceInstrumentRulesError,
    binance_exchange_symbol_rules,
)


INSTRUMENT_RULES_TIMEOUT_SECONDS = 10
INSTRUMENT_RULES_TTL_SECONDS = 60
_PERPETUAL_INSTRUMENT = re.compile(r"^[A-Z0-9]+-PERP$")


class InstrumentRulesUnavailable(RuntimeError):
    """Sanitized public-rule read failure."""


class BinanceExchangeInfoApi(Protocol):
    async def query_futures_exchange_info(self) -> object: ...


class InstrumentRulesProvider(Protocol):
    async def fetch(self, instrument_ref: str) -> InstrumentOrderRules: ...


def binance_public_instrument_rules_identity(
    profile: str,
) -> tuple[BinanceEnvironment, str]:
    """Resolve one exchange-info identity for the complete runtime profile."""

    if profile == "BINANCE_DEMO":
        return BinanceEnvironment.DEMO, "BINANCE_DEMO_EXCHANGE_INFO"
    if profile in {"BINANCE_LIVE_READ_ONLY", "BINANCE_LIVE_WRITE"}:
        return BinanceEnvironment.LIVE, "BINANCE_LIVE_EXCHANGE_INFO"
    raise ValueError("INSTRUMENT_RULES_PROFILE_UNSUPPORTED")


class BinancePublicInstrumentRules:
    """Fetch exchangeInfo only when a schedule is previewed, with a short TTL."""

    def __init__(
        self,
        profile: str,
        *,
        proxy_url: str | None = None,
        market_api: BinanceExchangeInfoApi | None = None,
        ttl_seconds: int = INSTRUMENT_RULES_TTL_SECONDS,
    ) -> None:
        environment, self._source = binance_public_instrument_rules_identity(profile)
        if market_api is None:
            client = get_cached_binance_http_client(
                clock=LiveClock(),
                account_type=BinanceAccountType.USDT_FUTURES,
                environment=environment,
                proxy_url=proxy_url,
            )
            market_api = BinanceFuturesMarketHttpAPI(
                client,
                BinanceAccountType.USDT_FUTURES,
            )
        self._market_api = market_api
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, InstrumentOrderRules]] = {}
        self._lock = asyncio.Lock()

    async def fetch(self, instrument_ref: str) -> InstrumentOrderRules:
        symbol = _symbol_for_instrument(instrument_ref)
        cached = self._cache.get(symbol)
        now = monotonic()
        if cached is not None and cached[0] > now:
            return cached[1]
        async with self._lock:
            cached = self._cache.get(symbol)
            now = monotonic()
            if cached is not None and cached[0] > now:
                return cached[1]
            return await self._query_and_cache(symbol)

    async def refresh(self, instrument_ref: str) -> InstrumentOrderRules:
        """Bypass the preview cache for an activation-time rule check."""

        symbol = _symbol_for_instrument(instrument_ref)
        async with self._lock:
            return await self._query_and_cache(symbol)

    async def _query_and_cache(self, symbol: str) -> InstrumentOrderRules:
        try:
            exchange_info = await asyncio.wait_for(
                self._market_api.query_futures_exchange_info(),
                timeout=INSTRUMENT_RULES_TIMEOUT_SECONDS,
            )
            rules = binance_exchange_symbol_rules(exchange_info, symbol)
            source_time_ms = getattr(exchange_info, "serverTime", None)
            if not isinstance(source_time_ms, int) or source_time_ms <= 0:
                raise BinanceInstrumentRulesError("INSTRUMENT_RULES_CUTOFF_UNKNOWN")
            result = InstrumentOrderRules(
                **rules.order_schedule_payload(),
                source=self._source,
                source_cutoff=datetime.fromtimestamp(
                    source_time_ms / 1000,
                    tz=UTC,
                ).isoformat(),
            )
        except InstrumentRulesUnavailable:
            raise
        except Exception as exc:
            raise InstrumentRulesUnavailable(
                f"INSTRUMENT_RULES_QUERY_FAILED_{type(exc).__name__.upper()}"
            ) from None
        self._cache[symbol] = (monotonic() + self._ttl_seconds, result)
        return result


def _symbol_for_instrument(instrument_ref: str) -> str:
    if not _PERPETUAL_INSTRUMENT.fullmatch(instrument_ref):
        raise InstrumentRulesUnavailable("INSTRUMENT_RULES_INSTRUMENT_UNSUPPORTED")
    return instrument_ref.removesuffix("-PERP")
