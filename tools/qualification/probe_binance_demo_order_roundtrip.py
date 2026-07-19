from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from nautilus_trader.adapters.binance import BINANCE
from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import BinanceLiveDataClientFactory
from nautilus_trader.adapters.binance import BinanceLiveExecClientFactory
from nautilus_trader.adapters.binance import get_cached_binance_http_client
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.common.enums import BinanceKeyType
from nautilus_trader.adapters.binance.factories import (
    get_cached_binance_futures_instrument_provider,
)
from nautilus_trader.adapters.binance.futures.http.account import (
    BinanceFuturesAccountHttpAPI,
)
from nautilus_trader.adapters.binance.http.error import BinanceError
from nautilus_trader.live.node import TradingNode
from nautilus_trader.trading.config import StrategyConfig

from tools.qualification.nautilus_fixtures import DemoOrderCapabilityStrategy
from tools.qualification.probe_binance_demo_clients import INSTRUMENT_IDS
from tools.qualification.probe_binance_demo_clients import INSTRUMENT_SYMBOLS
from tools.qualification.probe_binance_demo_clients import LOG_DIRECTORY
from tools.qualification.probe_binance_demo_clients import QualificationError
from tools.qualification.probe_binance_demo_clients import _acquire_executor_mutex
from tools.qualification.probe_binance_demo_clients import _build_configuration
from tools.qualification.probe_binance_demo_clients import _canonical_json
from tools.qualification.probe_binance_demo_clients import _load_credentials
from tools.qualification.probe_binance_demo_clients import _effective_leverage
from tools.qualification.probe_binance_demo_clients import _parse_finite_decimal_text
from tools.qualification.probe_binance_demo_clients import _release_executor_mutex
from tools.qualification.probe_binance_demo_clients import _scan_paths_for_credentials
from tools.qualification.probe_binance_demo_clients import _validate_proxy_url
from tools.qualification.probe_binance_demo_clients import _without_binance_credential_environment
from tools.qualification.probe_binance_demo_clients import _write_evidence


async def _responsibility_snapshot(
    account_api: BinanceFuturesAccountHttpAPI,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for symbol in INSTRUMENT_SYMBOLS:
        positions = await account_api.query_futures_position_risk(
            symbol=symbol,
            recv_window="5000",
        )
        ordinary_orders = await account_api.query_open_orders(
            symbol=symbol,
            recv_window="5000",
        )
        algo_orders = await account_api.query_open_algo_orders(
            symbol=symbol,
            recv_window="5000",
        )
        nonzero_positions = [
            position
            for position in positions
            if _parse_finite_decimal_text(position.positionAmt, "POSITION_AMOUNT") != 0
        ]
        result[symbol] = {
            "nonzero_position_count": len(nonzero_positions),
            "open_ordinary_order_count": len(ordinary_orders),
            "open_algo_order_count": len(algo_orders),
            "clear": not (nonzero_positions or ordinary_orders or algo_orders),
        }
    return result


def _all_clear(snapshot: dict[str, dict[str, object]]) -> bool:
    return all(bool(value["clear"]) for value in snapshot.values())


async def _query_algo_order_until_visible(
    account_api: BinanceFuturesAccountHttpAPI,
    client_order_id: str,
    *,
    max_attempts: int,
    delay_seconds: float,
) -> tuple[object | None, int, int]:
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")

    transient_error_count = 0
    for attempt in range(1, max_attempts + 1):
        try:
            venue_order = await account_api.query_algo_order(
                client_algo_id=client_order_id,
                recv_window="5000",
            )
        except BinanceError:
            transient_error_count += 1
        else:
            if venue_order is not None:
                return venue_order, attempt, transient_error_count
        if attempt < max_attempts:
            await asyncio.sleep(delay_seconds)
    return None, max_attempts, transient_error_count


async def _observe_round_trip(
    node: TradingNode,
    strategy: DemoOrderCapabilityStrategy,
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
    evidence: dict[str, object],
    errors: list[str],
) -> None:
    account_api: BinanceFuturesAccountHttpAPI | None = None
    try:
        ready = False
        for _ in range(700):
            ready = bool(
                node.is_running()
                and node.kernel.data_engine.check_connected()
                and node.kernel.exec_engine.check_connected()
                and len(node.cache.accounts()) == 1
                and all(node.cache.instrument(instrument_id) is not None for instrument_id in INSTRUMENT_IDS)
            )
            if ready:
                break
            await asyncio.sleep(0.05)
        if not ready:
            raise TimeoutError("NODE_CLIENT_INITIALIZATION_TIMEOUT")

        shared_http_client = get_cached_binance_http_client(
            clock=node.kernel.clock,
            account_type=BinanceAccountType.USDT_FUTURES,
            api_key=api_key,
            api_secret=api_secret,
            key_type=BinanceKeyType.HMAC,
            base_url=None,
            environment=BinanceEnvironment.DEMO,
            is_us=False,
            proxy_url=proxy_url,
        )
        account_api = BinanceFuturesAccountHttpAPI(
            shared_http_client,
            node.kernel.clock,
            BinanceAccountType.USDT_FUTURES,
        )

        hedge_mode = await account_api.query_futures_hedge_mode(recv_window="5000")
        if hedge_mode.dualSidePosition:
            errors.append("ACCOUNT_NOT_ONE_WAY")
        symbol_configs = await account_api.query_futures_symbol_config(recv_window="5000")
        configs_by_symbol = {config.symbol: config for config in symbol_configs}
        evidence["account_execution_policy"] = {
            "position_mode": "ONE_WAY" if not hedge_mode.dualSidePosition else "HEDGE",
            "account_settings_modified": False,
            "effective_leverage_formula": "min(actual_leverage, 5)",
            "crossed_or_actual_leverage_above_5_is_not_a_blocker": True,
            "symbols": {
                symbol: {
                    "actual_margin_mode": configs_by_symbol[symbol].marginType,
                    "actual_leverage": configs_by_symbol[symbol].leverage,
                    "effective_leverage": _effective_leverage(
                        configs_by_symbol[symbol].leverage,
                    ),
                }
                for symbol in INSTRUMENT_SYMBOLS
                if symbol in configs_by_symbol
            },
        }

        preflight = await _responsibility_snapshot(account_api)
        evidence["preflight"] = preflight
        if not _all_clear(preflight):
            errors.append("PREFLIGHT_EXTERNAL_OR_UNKNOWN_RESPONSIBILITY")
            return

        strategy.arm()
        evidence["armed_only_after_clear_preflight"] = True
        exchange_open_queries: dict[str, dict[str, object]] = {}
        exchange_open_query_attempts = {
            "ENTRY_LIMIT": 0,
            "ENTRY_STOP_MARKET": 0,
        }
        for _ in range(800):
            if "ENTRY_LIMIT" in strategy.accepted and "ENTRY_LIMIT" not in exchange_open_queries:
                order = strategy.orders["ENTRY_LIMIT"]
                exchange_open_query_attempts["ENTRY_LIMIT"] += 1
                try:
                    venue = await account_api.query_order(
                        symbol="BTCUSDT",
                        orig_client_order_id=order.client_order_id.value,
                        recv_window="5000",
                    )
                    if venue is None:
                        await asyncio.sleep(0.25)
                        continue
                    exchange_open_queries["ENTRY_LIMIT"] = {
                        "client_order_id_exact_round_trip": (
                            venue.clientOrderId == order.client_order_id.value
                        ),
                        "order_type": venue.type.value if venue.type is not None else None,
                        "status": venue.status.value if venue.status is not None else None,
                        "reduce_only": venue.reduceOnly,
                        "close_position": venue.closePosition,
                    }
                except BinanceError:
                    await asyncio.sleep(0.25)
            if (
                "ENTRY_STOP_MARKET" in strategy.accepted
                and "ENTRY_STOP_MARKET" not in exchange_open_queries
            ):
                order = strategy.orders["ENTRY_STOP_MARKET"]
                exchange_open_query_attempts["ENTRY_STOP_MARKET"] += 1
                venue, _attempts, _transient_errors = await _query_algo_order_until_visible(
                    account_api,
                    order.client_order_id.value,
                    max_attempts=1,
                    delay_seconds=0.0,
                )
                if venue is not None:
                    exchange_open_queries["ENTRY_STOP_MARKET"] = {
                        "client_order_id_exact_round_trip": (
                            venue.clientAlgoId == order.client_order_id.value
                        ),
                        "order_type": venue.orderType,
                        "status": venue.algoStatus,
                        "quantity_is_explicit": venue.quantity is not None,
                        "working_type": venue.workingType,
                        "reduce_only": venue.reduceOnly,
                        "close_position": venue.closePosition,
                    }
                else:
                    await asyncio.sleep(0.25)
            if strategy.done or strategy.errors:
                break
            await asyncio.sleep(0.05)

        evidence["exchange_open_queries"] = exchange_open_queries
        evidence["exchange_open_query_attempts"] = exchange_open_query_attempts
        if strategy.errors:
            errors.extend(strategy.errors)
        if not strategy.done:
            errors.append("ORDER_ROUND_TRIP_TIMEOUT")
            strategy.request_cleanup()
            for _ in range(200):
                if all(not order.is_open for order in strategy.orders.values()):
                    break
                await asyncio.sleep(0.05)

        terminal_queries: dict[str, dict[str, object]] = {}
        if "ENTRY_LIMIT" in strategy.orders:
            order = strategy.orders["ENTRY_LIMIT"]
            venue = await account_api.query_order(
                symbol="BTCUSDT",
                orig_client_order_id=order.client_order_id.value,
                recv_window="5000",
            )
            terminal_queries["ENTRY_LIMIT"] = {
                "client_order_id_exact_round_trip": (
                    venue.clientOrderId == order.client_order_id.value
                ),
                "status": venue.status.value if venue.status is not None else None,
            }
        if "ENTRY_STOP_MARKET" in strategy.orders:
            order = strategy.orders["ENTRY_STOP_MARKET"]
            venue, attempts, transient_errors = await _query_algo_order_until_visible(
                account_api,
                order.client_order_id.value,
                max_attempts=20,
                delay_seconds=0.25,
            )
            evidence["algo_terminal_query_visibility"] = {
                "attempts": attempts,
                "transient_errors": transient_errors,
                "visible": venue is not None,
                "same_uuid32_reused": True,
                "write_retried": False,
            }
            terminal_queries["ENTRY_STOP_MARKET"] = {
                "client_order_id_exact_round_trip": bool(
                    venue is not None and venue.clientAlgoId == order.client_order_id.value
                ),
                "status": None if venue is None else venue.algoStatus,
            }
        evidence["exchange_terminal_queries"] = terminal_queries
        if terminal_queries.get("ENTRY_LIMIT", {}).get("status") != "CANCELED":
            errors.append("LIMIT_TERMINAL_STATUS_NOT_CANCELED")
        if terminal_queries.get("ENTRY_STOP_MARKET", {}).get("status") != "CANCELED":
            errors.append("ALGO_TERMINAL_STATUS_NOT_CANCELED")

        await asyncio.sleep(0.25)
        postflight = await _responsibility_snapshot(account_api)
        evidence["postflight"] = postflight
        if not _all_clear(postflight):
            errors.append("POSTFLIGHT_RESPONSIBILITY_NOT_CLEAR")

        strategy_evidence = strategy.qualification_evidence()
        evidence["strategy"] = strategy_evidence
        required_profiles = {"ENTRY_LIMIT", "ENTRY_STOP_MARKET"}
        for field in ("accepted_profiles", "public_query_profiles", "canceled_profiles"):
            if set(strategy_evidence[field]) != required_profiles:
                errors.append(f"STRATEGY_{field.upper()}_MISMATCH")
        if not strategy_evidence["client_order_ids_are_uuid32"]:
            errors.append("CLIENT_ORDER_ID_FORMAT_MISMATCH")
        if set(exchange_open_queries) != required_profiles:
            errors.append("OPEN_QUERY_PROFILE_MISMATCH")
        if not all(
            bool(value["client_order_id_exact_round_trip"])
            for value in exchange_open_queries.values()
        ):
            errors.append("OPEN_QUERY_IDENTITY_MISMATCH")
        if not all(
            bool(value["client_order_id_exact_round_trip"])
            for value in terminal_queries.values()
        ):
            errors.append("TERMINAL_QUERY_IDENTITY_MISMATCH")
    finally:
        emergency_cleanup = {
            "ordinary_orders_canceled": 0,
            "algo_orders_canceled": 0,
            "used_fixed_package_account_wrapper": False,
        }
        try:
            if account_api is not None:
                strategy.request_cleanup()
                await asyncio.sleep(0.5)
                own_ids = {
                    order.client_order_id.value
                    for order in strategy.orders.values()
                }
                ordinary_orders = await account_api.query_open_orders(
                    symbol="BTCUSDT",
                    recv_window="5000",
                )
                for venue_order in ordinary_orders:
                    if venue_order.clientOrderId in own_ids:
                        await account_api.cancel_order(
                            symbol="BTCUSDT",
                            order_id=venue_order.orderId,
                            orig_client_order_id=None,
                            recv_window="5000",
                        )
                        emergency_cleanup["ordinary_orders_canceled"] += 1
                algo_orders = await account_api.query_open_algo_orders(
                    symbol="BTCUSDT",
                    recv_window="5000",
                )
                for venue_order in algo_orders:
                    if venue_order.clientAlgoId in own_ids:
                        await account_api.cancel_algo_order(
                            algo_id=venue_order.algoId,
                            client_algo_id=None,
                            recv_window="5000",
                        )
                        emergency_cleanup["algo_orders_canceled"] += 1
                if (
                    emergency_cleanup["ordinary_orders_canceled"]
                    or emergency_cleanup["algo_orders_canceled"]
                ):
                    emergency_cleanup["used_fixed_package_account_wrapper"] = True
                    errors.append("EMERGENCY_CLEANUP_REQUIRED")
        except Exception as cleanup_exc:
            errors.append(f"EMERGENCY_CLEANUP_FAILED:{type(cleanup_exc).__name__}")
        finally:
            evidence["emergency_cleanup"] = emergency_cleanup
            await node.stop_async()
            evidence["node_stopped"] = not node.is_running()


def _online_probe(evidence_path: Path | None, proxy_url: str | None) -> int:
    evidence: dict[str, object] = {
        "operation": "INITIALIZING",
        "profile": "BINANCE_DEMO",
        "scope": "DIRECT_MINIMUM_ORDINARY_AND_ALGO_WRITE_CAPABILITY",
        "actual_client_order_ids_persisted": False,
        "proxy": "RUNTIME_LOOPBACK_ARGUMENT" if proxy_url is not None else "DISABLED",
        "node_built": False,
        "node_stopped": False,
        "node_disposed": False,
    }
    errors: list[str] = []
    mutex = None
    loop: asyncio.AbstractEventLoop | None = None
    node: TradingNode | None = None
    api_key: str | None = None
    api_secret: str | None = None

    try:
        proxy_url = _validate_proxy_url(proxy_url)
        mutex = _acquire_executor_mutex()
        evidence["executor_mutex"] = "ACQUIRED_CURRENT_USER_PROTECTED_DACL"
        api_key, api_secret, backend_name = _load_credentials()
        evidence["credential_backend"] = backend_name
        with _without_binance_credential_environment() as environment_was_populated:
            evidence["credential_environment_sanitized"] = True
            evidence["credential_environment_had_values"] = environment_was_populated
            node_config, _provider_config, data_config, exec_config = _build_configuration(
                api_key,
                api_secret,
                proxy_url,
            )
            if exec_config.max_retries is not None:
                raise QualificationError("EXEC_WRITE_RETRIES_NOT_DISABLED")
            if data_config.proxy_url != proxy_url or exec_config.proxy_url != proxy_url:
                raise QualificationError("CLIENT_PROXY_CONFIGURATION_MISMATCH")

            LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            node = TradingNode(config=node_config, loop=loop)
            node.add_data_client_factory(BINANCE, BinanceLiveDataClientFactory)
            node.add_exec_client_factory(BINANCE, BinanceLiveExecClientFactory)
            node.build()
            evidence["node_built"] = node.is_built()
            strategy = DemoOrderCapabilityStrategy(
                config=StrategyConfig(
                    strategy_id="DIRECTORDER",
                    order_id_tag="001",
                    external_order_claims=None,
                    manage_contingent_orders=False,
                    manage_gtd_expiry=False,
                    manage_stop=False,
                ),
            )
            node.trader.add_strategy(strategy)
            observer_task = loop.create_task(
                _observe_round_trip(
                    node,
                    strategy,
                    api_key,
                    api_secret,
                    proxy_url,
                    evidence,
                    errors,
                ),
            )
            node.run(raise_exception=True)
            if observer_task.done():
                observer_task.result()
            else:
                errors.append("OBSERVER_TASK_NOT_COMPLETED")
                observer_task.cancel()

            evidence["node_stopped"] = not node.is_running()
            node.dispose()
            evidence["node_disposed"] = True
    except Exception as exc:
        if isinstance(exc, QualificationError):
            errors.append(f"DEMO_ORDER_PROBE_FAILED:{exc}")
        else:
            errors.append(f"DEMO_ORDER_PROBE_FAILED:{type(exc).__name__}")
        if node is not None:
            try:
                node.stop()
                evidence["node_stopped"] = not node.is_running()
            except Exception as cleanup_exc:
                errors.append(f"NODE_STOP_FAILED:{type(cleanup_exc).__name__}")
            try:
                node.dispose()
                evidence["node_disposed"] = True
            except Exception as cleanup_exc:
                errors.append(f"NODE_DISPOSE_FAILED:{type(cleanup_exc).__name__}")
    finally:
        asyncio.set_event_loop(None)
        if loop is not None and not loop.is_closed():
            loop.close()
        get_cached_binance_futures_instrument_provider.cache_clear()
        get_cached_binance_http_client.cache_clear()
        if mutex is not None:
            try:
                _release_executor_mutex(mutex)
            except Exception as exc:
                errors.append(f"EXECUTOR_MUTEX_RELEASE_FAILED:{type(exc).__name__}")

    if api_key is not None and api_secret is not None:
        scan_paths = [path for path in LOG_DIRECTORY.rglob("*") if path.is_file()]
        scanned, secret_found = _scan_paths_for_credentials(scan_paths, api_key, api_secret)
        evidence["secret_scan"] = {
            "files_scanned": scanned,
            "raw_credential_found": secret_found,
        }
        if secret_found:
            errors.append("RAW_CREDENTIAL_FOUND_IN_LOG")

    if evidence["node_built"] and not evidence["node_stopped"]:
        errors.append("NODE_NOT_STOPPED")
    if evidence["node_built"] and not evidence["node_disposed"]:
        errors.append("NODE_NOT_DISPOSED")
    evidence["errors"] = sorted(set(errors))
    evidence["status"] = "QUALIFIED" if not errors else "REJECTED"

    rendered = _canonical_json(evidence)
    if api_key is not None and api_key in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    elif api_secret is not None and api_secret in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    _write_evidence(evidence_path, evidence)
    return 0 if evidence.get("status") == "QUALIFIED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qualify one ordinary and one algo Binance Demo order round trip.",
    )
    parser.add_argument("--evidence-path", type=Path)
    parser.add_argument("--proxy-url")
    args = parser.parse_args()
    return _online_probe(args.evidence_path, args.proxy_url)


if __name__ == "__main__":
    raise SystemExit(main())
