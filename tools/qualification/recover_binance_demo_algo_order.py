from __future__ import annotations

import argparse
import asyncio
import json
import re
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
from nautilus_trader.common.component import LiveClock
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.trading.config import StrategyConfig

from tools.qualification.nautilus_fixtures import DemoExternalOrderRecoveryStrategy
from tools.qualification.probe_binance_demo_clients import INSTRUMENT_IDS
from tools.qualification.probe_binance_demo_clients import LOG_DIRECTORY
from tools.qualification.probe_binance_demo_clients import QualificationError
from tools.qualification.probe_binance_demo_clients import _acquire_executor_mutex
from tools.qualification.probe_binance_demo_clients import _build_configuration
from tools.qualification.probe_binance_demo_clients import _canonical_json
from tools.qualification.probe_binance_demo_clients import _load_credentials
from tools.qualification.probe_binance_demo_clients import _release_executor_mutex
from tools.qualification.probe_binance_demo_clients import _scan_paths_for_credentials
from tools.qualification.probe_binance_demo_clients import _validate_proxy_url
from tools.qualification.probe_binance_demo_clients import _without_binance_credential_environment
from tools.qualification.probe_binance_demo_clients import _write_evidence
from tools.qualification.probe_binance_demo_order_roundtrip import _all_clear
from tools.qualification.probe_binance_demo_order_roundtrip import _responsibility_snapshot


UUID32_PATTERN = re.compile(r"^[0-9a-f]{32}$")


async def _direct_emergency_cleanup_async(
    client_order_id: str,
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
    evidence: dict[str, object],
) -> None:
    clock = LiveClock()
    shared_http_client = get_cached_binance_http_client(
        clock=clock,
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
        clock,
        BinanceAccountType.USDT_FUTURES,
    )
    preflight = await _responsibility_snapshot(account_api)
    evidence["preflight"] = preflight
    open_algo_orders = await account_api.query_open_algo_orders(
        symbol="BTCUSDT",
        recv_window="5000",
    )
    matching = [order for order in open_algo_orders if order.clientAlgoId == client_order_id]
    evidence["original_identity_open_match_count"] = len(matching)
    if len(matching) != 1:
        raise QualificationError("ORIGINAL_ALGO_IDENTITY_NOT_EXACTLY_ONE_OPEN_ORDER")
    response = await account_api.cancel_algo_order(
        algo_id=matching[0].algoId,
        client_algo_id=None,
        recv_window="5000",
    )
    evidence["emergency_same_package_cancel"] = {
        "used_raw_http": False,
        "used_second_client": False,
        "used_fixed_package_account_wrapper": True,
        "used_venue_algo_id_only": True,
        "response_code": response.code,
        "identity_matched": response.clientAlgoId == client_order_id,
        "actual_identity_persisted": False,
    }
    for _ in range(40):
        current = await account_api.query_open_algo_orders(
            symbol="BTCUSDT",
            recv_window="5000",
        )
        if not any(order.clientAlgoId == client_order_id for order in current):
            break
        await asyncio.sleep(0.25)
    postflight = await _responsibility_snapshot(account_api)
    evidence["postflight"] = postflight
    evidence["responsibility_cleared"] = _all_clear(postflight)
    if not evidence["responsibility_cleared"]:
        raise QualificationError("RESPONSIBILITY_NOT_CLEARED")


def _run_direct_emergency(
    client_order_id: str,
    evidence_path: Path | None,
    proxy_url: str | None,
) -> int:
    evidence: dict[str, object] = {
        "operation": "DIRECT_ALGO_EMERGENCY_RESPONSIBILITY_CLEANUP",
        "profile": "BINANCE_DEMO",
        "original_identity_format_valid": True,
        "actual_identity_persisted": False,
        "proxy": "RUNTIME_LOOPBACK_ARGUMENT" if proxy_url is not None else "DISABLED",
        "public_strategy_path_qualified_by_this_run": False,
        "reason": "FULL_NODE_RECOVERY_TRANSPORT_FAILED_BEFORE_CANCEL",
    }
    errors: list[str] = []
    mutex = None
    api_key: str | None = None
    api_secret: str | None = None
    try:
        proxy_url = _validate_proxy_url(proxy_url)
        mutex = _acquire_executor_mutex()
        api_key, api_secret, backend_name = _load_credentials()
        evidence["credential_backend"] = backend_name
        with _without_binance_credential_environment() as environment_was_populated:
            evidence["credential_environment_sanitized"] = True
            evidence["credential_environment_had_values"] = environment_was_populated
            asyncio.run(
                _direct_emergency_cleanup_async(
                    client_order_id,
                    api_key,
                    api_secret,
                    proxy_url,
                    evidence,
                ),
            )
    except Exception as exc:
        if isinstance(exc, QualificationError):
            errors.append(f"EMERGENCY_CLEANUP_FAILED:{exc}")
        else:
            errors.append(f"EMERGENCY_CLEANUP_FAILED:{type(exc).__name__}")
    finally:
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
    evidence["errors"] = sorted(set(errors))
    evidence["status"] = (
        "RESPONSIBILITY_CLEARED_QUALIFICATION_REJECTED"
        if evidence.get("responsibility_cleared")
        else "RECOVERY_FAILED"
    )
    rendered = _canonical_json(evidence)
    if client_order_id in rendered:
        evidence = {"status": "RECOVERY_FAILED", "errors": ["EVIDENCE_IDENTITY_LEAK_GUARD"]}
    elif api_key is not None and api_key in rendered:
        evidence = {"status": "RECOVERY_FAILED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    elif api_secret is not None and api_secret in rendered:
        evidence = {"status": "RECOVERY_FAILED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    _write_evidence(evidence_path, evidence)
    return 0 if evidence.get("responsibility_cleared") else 1


async def _recover(
    node: TradingNode,
    strategy: DemoExternalOrderRecoveryStrategy,
    client_order_id: str,
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
    evidence: dict[str, object],
    errors: list[str],
) -> None:
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
        preflight = await _responsibility_snapshot(account_api)
        evidence["preflight"] = preflight

        open_algo_orders = await account_api.query_open_algo_orders(
            symbol="BTCUSDT",
            recv_window="5000",
        )
        matching = [order for order in open_algo_orders if order.clientAlgoId == client_order_id]
        evidence["original_identity_open_match_count"] = len(matching)
        if len(matching) != 1:
            raise QualificationError("ORIGINAL_ALGO_IDENTITY_NOT_EXACTLY_ONE_OPEN_ORDER")
        venue_algo_id = matching[0].algoId

        cache_order = node.cache.order(ClientOrderId(client_order_id))
        evidence["startup_reconciliation"] = {
            "cache_order_found_by_original_uuid32": cache_order is not None,
            "technical_strategy_id": None if cache_order is None else str(cache_order.strategy_id),
            "venue_order_id_present": bool(
                cache_order is not None and cache_order.venue_order_id is not None
            ),
            "actual_identity_persisted": False,
        }

        public_cancel_cleared = False
        if cache_order is not None:
            strategy.cancel_reconciled_order(cache_order)
            for _ in range(40):
                current = await account_api.query_open_algo_orders(
                    symbol="BTCUSDT",
                    recv_window="5000",
                )
                if not any(order.clientAlgoId == client_order_id for order in current):
                    public_cancel_cleared = True
                    break
                await asyncio.sleep(0.25)
        evidence["public_strategy_cancel"] = {
            "called": strategy.cancel_called,
            "cleared_original_open_algo_order": public_cancel_cleared,
        }

        emergency_cancel_required = not public_cancel_cleared
        evidence["emergency_same_package_cancel_required"] = emergency_cancel_required
        if emergency_cancel_required:
            errors.append("PUBLIC_STRATEGY_CANCEL_DID_NOT_CLEAR_ALGO_ORDER")
            response = await account_api.cancel_algo_order(
                algo_id=venue_algo_id,
                client_algo_id=None,
                recv_window="5000",
            )
            evidence["emergency_same_package_cancel"] = {
                "used_raw_http": False,
                "used_second_client": False,
                "used_fixed_package_account_wrapper": True,
                "used_venue_algo_id_only": True,
                "response_code": response.code,
                "identity_matched": response.clientAlgoId == client_order_id,
                "actual_identity_persisted": False,
            }

        for _ in range(40):
            current = await account_api.query_open_algo_orders(
                symbol="BTCUSDT",
                recv_window="5000",
            )
            if not any(order.clientAlgoId == client_order_id for order in current):
                break
            await asyncio.sleep(0.25)
        postflight = await _responsibility_snapshot(account_api)
        evidence["postflight"] = postflight
        evidence["responsibility_cleared"] = _all_clear(postflight)
        if not evidence["responsibility_cleared"]:
            errors.append("RESPONSIBILITY_NOT_CLEARED")
    finally:
        await node.stop_async()
        evidence["node_stopped"] = not node.is_running()


def _run(
    client_order_id: str,
    evidence_path: Path | None,
    proxy_url: str | None,
) -> int:
    if UUID32_PATTERN.fullmatch(client_order_id) is None:
        raise SystemExit("client-order-id must be UUID32 lowercase hexadecimal")
    evidence: dict[str, object] = {
        "operation": "DIRECT_ALGO_RESPONSIBILITY_RECOVERY",
        "profile": "BINANCE_DEMO",
        "original_identity_format_valid": True,
        "actual_identity_persisted": False,
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
            strategy = DemoExternalOrderRecoveryStrategy(
                config=StrategyConfig(
                    strategy_id="DIRECTRECOVER",
                    order_id_tag="001",
                    external_order_claims=None,
                    manage_contingent_orders=False,
                    manage_gtd_expiry=False,
                    manage_stop=False,
                ),
            )
            node.trader.add_strategy(strategy)
            observer_task = loop.create_task(
                _recover(
                    node,
                    strategy,
                    client_order_id,
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
            errors.append(f"ALGO_RECOVERY_FAILED:{exc}")
        else:
            errors.append(f"ALGO_RECOVERY_FAILED:{type(exc).__name__}")
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
    if evidence.get("responsibility_cleared") and errors:
        evidence["status"] = "RESPONSIBILITY_CLEARED_QUALIFICATION_REJECTED"
    elif evidence.get("responsibility_cleared"):
        evidence["status"] = "RESPONSIBILITY_CLEARED"
    else:
        evidence["status"] = "RECOVERY_FAILED"

    rendered = _canonical_json(evidence)
    if client_order_id in rendered:
        evidence = {"status": "RECOVERY_FAILED", "errors": ["EVIDENCE_IDENTITY_LEAK_GUARD"]}
    elif api_key is not None and api_key in rendered:
        evidence = {"status": "RECOVERY_FAILED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    elif api_secret is not None and api_secret in rendered:
        evidence = {"status": "RECOVERY_FAILED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    _write_evidence(evidence_path, evidence)
    return 0 if evidence.get("responsibility_cleared") else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recover one known Binance Demo algo order by its original UUID32.",
    )
    parser.add_argument("--client-order-id", required=True)
    parser.add_argument("--evidence-path", type=Path)
    parser.add_argument("--proxy-url")
    parser.add_argument("--emergency-direct", action="store_true")
    args = parser.parse_args()
    if UUID32_PATTERN.fullmatch(args.client_order_id) is None:
        raise SystemExit("client-order-id must be UUID32 lowercase hexadecimal")
    if args.emergency_direct:
        return _run_direct_emergency(
            args.client_order_id,
            args.evidence_path,
            args.proxy_url,
        )
    return _run(args.client_order_id, args.evidence_path, args.proxy_url)


if __name__ == "__main__":
    raise SystemExit(main())
