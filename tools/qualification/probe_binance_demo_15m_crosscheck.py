from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import get_cached_binance_http_client
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.common.enums import BinanceKlineInterval
from nautilus_trader.adapters.binance.futures.http.market import BinanceFuturesMarketHttpAPI
from nautilus_trader.common.component import LiveClock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.qualification.probe_binance_demo_clients import BINANCE_USDM_DEMO_BASE_URL
from tools.qualification.probe_binance_demo_clients import _validate_proxy_url
from tools.qualification.probe_binance_demo_clients import _write_evidence


SYMBOLS = ("BTCUSDT", "ETHUSDT")
FIFTEEN_MINUTES_MS = 15 * 60 * 1000
ONE_MINUTE_MS = 60 * 1000


def _sum_decimal(values: list[str]) -> Decimal:
    return sum((Decimal(value) for value in values), start=Decimal(0))


def _compare_15m_with_1m(one_minute: list[object], fifteen_minute: object) -> dict[str, bool]:
    ordered = sorted(one_minute, key=lambda value: value.open_time)
    expected_open_times = [
        fifteen_minute.open_time + index * ONE_MINUTE_MS
        for index in range(15)
    ]
    return {
        "exactly_fifteen_source_bars": len(ordered) == 15,
        "source_open_times_contiguous": (
            [value.open_time for value in ordered] == expected_open_times
        ),
        "interval_identity_matches": bool(
            ordered
            and ordered[0].open_time == fifteen_minute.open_time
            and ordered[-1].close_time == fifteen_minute.close_time
        ),
        "open_matches": bool(ordered and Decimal(ordered[0].open) == Decimal(fifteen_minute.open)),
        "high_matches": bool(
            ordered
            and max(Decimal(value.high) for value in ordered) == Decimal(fifteen_minute.high)
        ),
        "low_matches": bool(
            ordered
            and min(Decimal(value.low) for value in ordered) == Decimal(fifteen_minute.low)
        ),
        "close_matches": bool(
            ordered and Decimal(ordered[-1].close) == Decimal(fifteen_minute.close)
        ),
        "base_volume_matches": bool(
            ordered
            and _sum_decimal([value.volume for value in ordered])
            == Decimal(fifteen_minute.volume)
        ),
        "quote_volume_matches": bool(
            ordered
            and _sum_decimal([value.asset_volume for value in ordered])
            == Decimal(fifteen_minute.asset_volume)
        ),
        "trade_count_matches": bool(
            ordered
            and sum(value.trades_count for value in ordered) == fifteen_minute.trades_count
        ),
        "taker_base_volume_matches": bool(
            ordered
            and _sum_decimal([value.taker_base_volume for value in ordered])
            == Decimal(fifteen_minute.taker_base_volume)
        ),
        "taker_quote_volume_matches": bool(
            ordered
            and _sum_decimal([value.taker_quote_volume for value in ordered])
            == Decimal(fifteen_minute.taker_quote_volume)
        ),
    }


async def _run(proxy_url: str | None) -> dict[str, object]:
    proxy_url = _validate_proxy_url(proxy_url)
    clock = LiveClock()
    client = get_cached_binance_http_client(
        clock=clock,
        account_type=BinanceAccountType.USDT_FUTURES,
        api_key=None,
        api_secret=None,
        environment=BinanceEnvironment.DEMO,
        proxy_url=proxy_url,
    )
    errors: list[str] = []
    if client.base_url != BINANCE_USDM_DEMO_BASE_URL:
        errors.append("PUBLIC_CLIENT_NOT_BOUND_TO_USDM_DEMO_BASE_URL")

    market = BinanceFuturesMarketHttpAPI(client, BinanceAccountType.USDT_FUTURES)
    latest_closed_open_ms = (
        clock.timestamp_ms() // FIFTEEN_MINUTES_MS - 1
    ) * FIFTEEN_MINUTES_MS
    latest_closed_end_ms = latest_closed_open_ms + FIFTEEN_MINUTES_MS - 1
    instruments: dict[str, object] = {}
    for symbol in SYMBOLS:
        one_minute = await market.query_klines(
            symbol=symbol,
            interval=BinanceKlineInterval.MINUTE_1,
            limit=15,
            start_time=latest_closed_open_ms,
            end_time=latest_closed_end_ms,
        )
        fifteen_minute = await market.query_klines(
            symbol=symbol,
            interval=BinanceKlineInterval.MINUTE_15,
            limit=1,
            start_time=latest_closed_open_ms,
            end_time=latest_closed_end_ms,
        )
        if len(fifteen_minute) != 1:
            errors.append(f"OFFICIAL_15M_SAMPLE_COUNT_MISMATCH:{symbol}")
            checks: dict[str, bool] = {}
        else:
            checks = _compare_15m_with_1m(one_minute, fifteen_minute[0])
            errors.extend(
                f"OFFICIAL_15M_CROSSCHECK_FAILED:{symbol}:{name}"
                for name, passed in checks.items()
                if not passed
            )
        instruments[symbol] = {
            "one_minute_sample_count": len(one_minute),
            "fifteen_minute_sample_count": len(fifteen_minute),
            "checks": checks,
        }

    return {
        "stage": "B00_BINANCE_DEMO_OFFICIAL_15M_CROSSCHECK",
        "scope": "PUBLIC_MARKET_DATA_READ_ONLY",
        "profile": "BINANCE_USDM_DEMO",
        "transport": {
            "proxy": "RUNTIME_LOOPBACK_ARGUMENT" if proxy_url is not None else None,
        },
        "fixed_package_wrapper": "BinanceFuturesMarketHttpAPI.query_klines",
        "http_method": "GET",
        "runtime_data_source_added": False,
        "persistent_market_data_added": False,
        "credentials_loaded": False,
        "account_or_order_endpoint_called": False,
        "decimal_comparison_without_float": True,
        "window": {
            "latest_fully_closed_15m": True,
            "start_ms": latest_closed_open_ms,
            "end_ms": latest_closed_end_ms,
        },
        "instruments": instruments,
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-check official Binance Demo 1m and 15m closed klines.",
    )
    parser.add_argument("--proxy-url")
    parser.add_argument("--evidence-path", type=Path)
    args = parser.parse_args()
    try:
        evidence = asyncio.run(_run(args.proxy_url))
    except Exception as exc:
        evidence = {
            "stage": "B00_BINANCE_DEMO_OFFICIAL_15M_CROSSCHECK",
            "errors": [f"PROBE_FAILED:{type(exc).__name__}"],
            "status": "REJECTED",
        }
    finally:
        get_cached_binance_http_client.cache_clear()
    _write_evidence(args.evidence_path, evidence)
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
