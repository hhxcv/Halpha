from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import re
import sys
from decimal import Decimal
from decimal import InvalidOperation
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import get_cached_binance_http_client
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.common.enums import BinanceKeyType
from nautilus_trader.adapters.binance.futures.http.account import BinanceFuturesAccountHttpAPI
from nautilus_trader.adapters.binance.futures.http.account import BinanceFuturesAllAlgoOrdersHttp
from nautilus_trader.adapters.binance.http.account import BinanceAllOrdersHttp
from nautilus_trader.adapters.binance.http.endpoint import BinanceHttpEndpoint
from nautilus_trader.common.component import LiveClock

from tools.qualification.probe_binance_demo_clients import BINANCE_USDM_DEMO_BASE_URL
from tools.qualification.probe_binance_demo_clients import QualificationError
from tools.qualification.probe_binance_demo_clients import _acquire_executor_mutex
from tools.qualification.probe_binance_demo_clients import _canonical_json
from tools.qualification.probe_binance_demo_clients import _load_credentials
from tools.qualification.probe_binance_demo_clients import _release_executor_mutex
from tools.qualification.probe_binance_demo_clients import _validate_proxy_url
from tools.qualification.probe_binance_demo_clients import _without_binance_credential_environment
from tools.qualification.probe_binance_demo_clients import _write_evidence


SYMBOLS = ("BTCUSDT", "ETHUSDT")
UUID32 = re.compile(r"^[0-9a-f]{32}$")
LOOKBACK_MS = 7 * 24 * 60 * 60 * 1000
PAGE_LIMIT = 100


def _is_decimal_text(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return False
    return parsed.is_finite()


def _ordinary_shape(order: object, symbol: str) -> bool:
    return bool(
        order.symbol == symbol
        and type(order.orderId) is int
        and isinstance(order.clientOrderId, str)
        and order.status is not None
        and order.type is not None
        and order.side is not None
        and _is_decimal_text(order.origQty)
        and _is_decimal_text(order.executedQty)
        and isinstance(order.reduceOnly, bool)
        and isinstance(order.closePosition, bool)
    )


def _algo_shape(order: object, symbol: str) -> bool:
    return bool(
        order.symbol == symbol
        and type(order.algoId) is int
        and isinstance(order.clientAlgoId, str)
        and isinstance(order.orderType, str)
        and isinstance(order.side, str)
        and isinstance(order.algoStatus, str)
        and _is_decimal_text(order.quantity)
        and isinstance(order.reduceOnly, bool)
        and isinstance(order.closePosition, bool)
    )


def _source_contract() -> dict[str, bool]:
    ordinary = inspect.getsource(BinanceAllOrdersHttp)
    algorithm = inspect.getsource(BinanceFuturesAllAlgoOrdersHttp)
    ordinary_wrapper = inspect.getsource(BinanceFuturesAccountHttpAPI.query_all_orders)
    algorithm_wrapper = inspect.getsource(BinanceFuturesAccountHttpAPI.query_all_algo_orders)
    endpoint = inspect.getsource(BinanceHttpEndpoint._method)
    return {
        "ordinary_endpoint_get_only_user_data": (
            'HttpMethod.GET: BinanceSecurityType.USER_DATA' in ordinary
            and 'base_endpoint + "allOrders"' in ordinary
        ),
        "algorithm_endpoint_get_only_user_data": (
            'HttpMethod.GET: BinanceSecurityType.USER_DATA' in algorithm
            and 'base_endpoint + "allAlgoOrders"' in algorithm
        ),
        "ordinary_wrapper_exposes_bounded_cursor": (
            "order_id: int | None" in ordinary_wrapper
            and "limit: int | None" in ordinary_wrapper
            and "orderId=order_id" in ordinary_wrapper
            and "limit=limit" in ordinary_wrapper
        ),
        "algorithm_wrapper_exposes_one_based_page_and_limit": (
            "page: int | None" in algorithm_wrapper
            and "limit: int | None" in algorithm_wrapper
            and "page=page" in algorithm_wrapper
            and "limit=limit" in algorithm_wrapper
        ),
        "per_endpoint_and_global_rate_limit_keys": (
            "default_keys.append(self._ratelimiter_key)" in endpoint
            and 'default_keys.append("binance:global")' in endpoint
        ),
    }


async def _query(
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
) -> dict[str, object]:
    clock = LiveClock()
    client = get_cached_binance_http_client(
        clock=clock,
        account_type=BinanceAccountType.USDT_FUTURES,
        api_key=api_key,
        api_secret=api_secret,
        key_type=BinanceKeyType.HMAC,
        environment=BinanceEnvironment.DEMO,
        proxy_url=proxy_url,
    )
    if client.base_url != BINANCE_USDM_DEMO_BASE_URL:
        raise QualificationError("ORDER_READ_CLIENT_NOT_BOUND_TO_USDM_DEMO")
    account = BinanceFuturesAccountHttpAPI(
        client,
        clock,
        BinanceAccountType.USDT_FUTURES,
    )
    cutoff_ms = clock.timestamp_ms()
    start_ms = cutoff_ms - LOOKBACK_MS
    instruments: dict[str, object] = {}
    errors: list[str] = []
    for symbol in SYMBOLS:
        ordinary = await account.query_all_orders(
            symbol=symbol,
            start_time=start_ms,
            end_time=cutoff_ms,
            limit=PAGE_LIMIT,
            recv_window="5000",
        )
        ordinary_ids = [order.orderId for order in ordinary]
        ordinary_shape_valid = all(_ordinary_shape(order, symbol) for order in ordinary)
        if not ordinary_shape_valid:
            errors.append(f"ORDINARY_ORDER_SCHEMA_MISMATCH:{symbol}")
        if len(set(ordinary_ids)) != len(ordinary_ids):
            errors.append(f"ORDINARY_ORDER_IDENTITY_DUPLICATE:{symbol}")

        algo_page_1 = await account.query_all_algo_orders(
            symbol=symbol,
            start_time=start_ms,
            end_time=cutoff_ms,
            page=1,
            limit=PAGE_LIMIT,
            recv_window="5000",
        )
        algo_page_2 = (
            await account.query_all_algo_orders(
                symbol=symbol,
                start_time=start_ms,
                end_time=cutoff_ms,
                page=2,
                limit=PAGE_LIMIT,
                recv_window="5000",
            )
            if len(algo_page_1) == PAGE_LIMIT
            else []
        )
        algorithms = [*algo_page_1, *algo_page_2]
        algo_ids = [order.algoId for order in algorithms]
        algo_shape_valid = all(_algo_shape(order, symbol) for order in algorithms)
        if not algo_shape_valid:
            errors.append(f"ALGO_ORDER_SCHEMA_MISMATCH:{symbol}")
        if len(set(algo_ids)) != len(algo_ids):
            errors.append(f"ALGO_ORDER_IDENTITY_DUPLICATE:{symbol}")

        instruments[symbol] = {
            "ordinary": {
                "path": "/fapi/v1/allOrders",
                "pagination": "ORDER_ID_CURSOR_IF_LIMIT_REACHED",
                "page_limit": PAGE_LIMIT,
                "record_count": len(ordinary),
                "short_page_terminates": len(ordinary) < PAGE_LIMIT,
                "schema_valid": ordinary_shape_valid,
                "identity_unique": len(set(ordinary_ids)) == len(ordinary_ids),
                "uuid32_identity_count": sum(
                    int(UUID32.fullmatch(order.clientOrderId) is not None)
                    for order in ordinary
                ),
            },
            "algorithm": {
                "path": "/fapi/v1/allAlgoOrders",
                "pagination": "ONE_BASED_PAGE_AND_LIMIT",
                "page_limit": PAGE_LIMIT,
                "page_sizes": [
                    len(algo_page_1),
                    *([len(algo_page_2)] if len(algo_page_1) == PAGE_LIMIT else []),
                ],
                "short_page_terminates": len(algo_page_1) < PAGE_LIMIT,
                "second_page_requested": len(algo_page_1) == PAGE_LIMIT,
                "record_count": len(algorithms),
                "schema_valid": algo_shape_valid,
                "identity_unique": len(set(algo_ids)) == len(algo_ids),
                "uuid32_identity_count": sum(
                    int(UUID32.fullmatch(order.clientAlgoId) is not None)
                    for order in algorithms
                ),
            },
        }
    return {
        "window_days": 7,
        "instruments": instruments,
        "source_contract": _source_contract(),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qualify read-only ordinary and algorithm order history matrices.",
    )
    parser.add_argument("--proxy-url")
    parser.add_argument("--evidence-path", type=Path)
    args = parser.parse_args()
    evidence: dict[str, object] = {
        "stage": "B00_BINANCE_DEMO_ORDER_READ_MATRIX",
        "profile": "BINANCE_USDM_DEMO",
        "read_only": True,
        "write_method_called": False,
        "actual_order_identities_persisted": False,
        "proxy": "RUNTIME_LOOPBACK_ARGUMENT" if args.proxy_url is not None else "DISABLED",
    }
    errors: list[str] = []
    mutex = None
    api_key: str | None = None
    api_secret: str | None = None
    try:
        proxy_url = _validate_proxy_url(args.proxy_url)
        mutex = _acquire_executor_mutex()
        api_key, api_secret, backend = _load_credentials()
        evidence["credential_backend"] = backend
        with _without_binance_credential_environment() as environment_was_populated:
            evidence["credential_environment_sanitized"] = True
            evidence["credential_environment_had_values"] = environment_was_populated
            result = asyncio.run(_query(api_key, api_secret, proxy_url))
            evidence.update(result)
            errors.extend(result["errors"])
            errors.extend(
                name
                for name, passed in result["source_contract"].items()
                if not passed
            )
    except Exception as exc:
        errors.append(f"ORDER_READ_MATRIX_FAILED:{type(exc).__name__}")
    finally:
        get_cached_binance_http_client.cache_clear()
        if mutex is not None:
            try:
                _release_executor_mutex(mutex)
            except Exception as exc:
                errors.append(f"EXECUTOR_MUTEX_RELEASE_FAILED:{type(exc).__name__}")
    evidence["errors"] = sorted(set(errors))
    evidence["status"] = "QUALIFIED" if not errors else "REJECTED"
    rendered = _canonical_json(evidence)
    if api_key is not None and api_key in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    elif api_secret is not None and api_secret in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    _write_evidence(args.evidence_path, evidence)
    return 0 if evidence.get("status") == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
