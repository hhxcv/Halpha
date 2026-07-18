from __future__ import annotations

import argparse
import asyncio
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
from tools.qualification.nautilus_fixtures import DemoRestartSeedStrategy
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
from tools.qualification.probe_binance_demo_order_roundtrip import (
    _query_algo_order_until_visible,
)
from tools.qualification.probe_binance_demo_order_roundtrip import _responsibility_snapshot


EXPECTED_PROFILES = {"KNOWN_ORDINARY", "KNOWN_ALGO", "UNKNOWN_SENTINEL"}
KNOWN_RECOVERY_PROFILES = {"KNOWN_ORDINARY", "KNOWN_ALGO"}


async def _wait_for_node_ready(node: TradingNode) -> None:
    for _ in range(700):
        if (
            node.is_running()
            and node.kernel.data_engine.check_connected()
            and node.kernel.exec_engine.check_connected()
            and len(node.cache.accounts()) == 1
            and all(node.cache.instrument(instrument_id) is not None for instrument_id in INSTRUMENT_IDS)
        ):
            return
        await asyncio.sleep(0.05)
    raise TimeoutError("NODE_CLIENT_INITIALIZATION_TIMEOUT")


def _account_api(
    node: TradingNode,
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
) -> BinanceFuturesAccountHttpAPI:
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
    return BinanceFuturesAccountHttpAPI(
        shared_http_client,
        node.kernel.clock,
        BinanceAccountType.USDT_FUTURES,
    )


async def _open_identity_presence(
    account_api: BinanceFuturesAccountHttpAPI,
    identities: dict[str, str],
) -> dict[str, bool]:
    ordinary = await account_api.query_open_orders(symbol="BTCUSDT", recv_window="5000")
    algo = await account_api.query_open_algo_orders(symbol="BTCUSDT", recv_window="5000")
    ordinary_ids = {order.clientOrderId for order in ordinary}
    algo_ids = {order.clientAlgoId for order in algo}
    return {
        profile: (
            client_order_id in algo_ids
            if profile == "KNOWN_ALGO"
            else client_order_id in ordinary_ids
        )
        for profile, client_order_id in identities.items()
    }


async def _seed_phase(
    node: TradingNode,
    strategy: DemoRestartSeedStrategy,
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
    identities: dict[str, str],
    evidence: dict[str, object],
    errors: list[str],
) -> None:
    try:
        await _wait_for_node_ready(node)
        account_api = _account_api(node, api_key, api_secret, proxy_url)
        preflight = await _responsibility_snapshot(account_api)
        evidence["seed_preflight"] = preflight
        if not _all_clear(preflight):
            errors.append("SEED_PREFLIGHT_EXTERNAL_OR_UNKNOWN_RESPONSIBILITY")
            return

        strategy.arm()
        evidence["seed_armed_only_after_clear_preflight"] = True
        for _ in range(800):
            if strategy.orders:
                identities.update(
                    {
                        profile: order.client_order_id.value
                        for profile, order in strategy.orders.items()
                    },
                )
            if strategy.accepted == EXPECTED_PROFILES or strategy.errors:
                break
            await asyncio.sleep(0.05)

        evidence["seed"] = {
            "profiles_created": sorted(strategy.orders),
            "profiles_accepted": sorted(strategy.accepted),
            "uuid32_format_valid": bool(strategy.orders)
            and all(
                len(order.client_order_id.value) == 32
                and order.client_order_id.value.isascii()
                and order.client_order_id.value.islower()
                and all(character in "0123456789abcdef" for character in order.client_order_id.value)
                for order in strategy.orders.values()
            ),
            "actual_client_order_ids_persisted": False,
        }
        if strategy.errors:
            errors.extend(strategy.errors)
        if strategy.accepted != EXPECTED_PROFILES:
            errors.append("SEED_ACCEPTED_PROFILE_MISMATCH")
        if set(identities) != EXPECTED_PROFILES:
            errors.append("SEED_IDENTITY_PROFILE_MISMATCH")
            return

        presence = await _open_identity_presence(account_api, identities)
        evidence["seed_open_visibility"] = presence
        if not all(presence.values()):
            errors.append("SEED_OPEN_VISIBILITY_INCOMPLETE")
    finally:
        await node.stop_async()


async def _recovery_phase(
    node: TradingNode,
    strategy: DemoExternalOrderRecoveryStrategy,
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
    identities: dict[str, str],
    evidence: dict[str, object],
    errors: list[str],
) -> None:
    try:
        await _wait_for_node_ready(node)
        account_api = _account_api(node, api_key, api_secret, proxy_url)
        startup_presence = await _open_identity_presence(account_api, identities)
        evidence["restart_open_visibility"] = startup_presence
        if not all(startup_presence.values()):
            errors.append("RESTART_OPEN_VISIBILITY_INCOMPLETE")

        cache_orders: dict[str, object | None] = {}
        cache_wait_attempts = 0
        for cache_wait_attempts in range(1, 151):
            cache_orders = {
                profile: node.cache.order(ClientOrderId(client_order_id))
                for profile, client_order_id in identities.items()
            }
            if all(order is not None for order in cache_orders.values()):
                break
            await asyncio.sleep(0.1)
        evidence["startup_reconciliation"] = {
            profile: {
                "cache_order_found_by_original_uuid32": order is not None,
                "technical_strategy_id": None if order is None else str(order.strategy_id),
                "venue_order_id_present": bool(order is not None and order.venue_order_id is not None),
            }
            for profile, order in cache_orders.items()
        }
        evidence["startup_reconciliation"]["cache_wait_attempts"] = cache_wait_attempts
        if not all(order is not None for order in cache_orders.values()):
            errors.append("RESTART_CACHE_ORDER_MISSING")
            return
        if not all(str(order.strategy_id) == "EXTERNAL" for order in cache_orders.values()):
            errors.append("RESTART_TECHNICAL_STRATEGY_ID_NOT_EXTERNAL")

        for profile in sorted(KNOWN_RECOVERY_PROFILES):
            order = cache_orders[profile]
            strategy.query_reconciled_order(order)
        await asyncio.sleep(0.5)
        for profile in sorted(KNOWN_RECOVERY_PROFILES):
            order = cache_orders[profile]
            strategy.cancel_reconciled_order(order)

        known_cleared_presence: dict[str, bool] | None = None
        for _ in range(80):
            known_cleared_presence = await _open_identity_presence(account_api, identities)
            if (
                not known_cleared_presence["KNOWN_ORDINARY"]
                and not known_cleared_presence["KNOWN_ALGO"]
            ):
                break
            await asyncio.sleep(0.25)
        assert known_cleared_presence is not None
        evidence["known_recovery_result"] = {
            "known_ordinary_cleared": not known_cleared_presence["KNOWN_ORDINARY"],
            "known_algo_cleared": not known_cleared_presence["KNOWN_ALGO"],
            "unknown_sentinel_remained_open": known_cleared_presence["UNKNOWN_SENTINEL"],
            "public_query_calls": strategy.query_call_count,
            "public_cancel_calls": strategy.cancel_call_count,
            "same_uuid32_reused": True,
            "write_retried": False,
        }
        if known_cleared_presence["KNOWN_ORDINARY"]:
            errors.append("PUBLIC_RESTART_CANCEL_DID_NOT_CLEAR_ORDINARY")
        if known_cleared_presence["KNOWN_ALGO"]:
            errors.append("PUBLIC_RESTART_CANCEL_DID_NOT_CLEAR_ALGO")
        if not known_cleared_presence["UNKNOWN_SENTINEL"]:
            errors.append("UNKNOWN_SENTINEL_WAS_INADVERTENTLY_CANCELED")

        sentinel_order = cache_orders["UNKNOWN_SENTINEL"]
        strategy.query_reconciled_order(sentinel_order)
        await asyncio.sleep(0.25)
        strategy.cancel_reconciled_order(sentinel_order)
        for _ in range(80):
            final_presence = await _open_identity_presence(account_api, identities)
            if not any(final_presence.values()):
                break
            await asyncio.sleep(0.25)
        else:
            final_presence = await _open_identity_presence(account_api, identities)
        evidence["fixture_cleanup_via_public_strategy"] = {
            "all_seed_identities_cleared": not any(final_presence.values()),
            "actual_client_order_ids_persisted": False,
        }

        terminal_ordinary = await account_api.query_order(
            symbol="BTCUSDT",
            orig_client_order_id=identities["KNOWN_ORDINARY"],
            recv_window="5000",
        )
        terminal_sentinel = await account_api.query_order(
            symbol="BTCUSDT",
            orig_client_order_id=identities["UNKNOWN_SENTINEL"],
            recv_window="5000",
        )
        terminal_algo, attempts, transient_errors = await _query_algo_order_until_visible(
            account_api,
            identities["KNOWN_ALGO"],
            max_attempts=20,
            delay_seconds=0.25,
        )
        evidence["terminal_queries"] = {
            "KNOWN_ORDINARY": None if terminal_ordinary is None else terminal_ordinary.status.value,
            "KNOWN_ALGO": None if terminal_algo is None else terminal_algo.algoStatus,
            "UNKNOWN_SENTINEL": None if terminal_sentinel is None else terminal_sentinel.status.value,
            "algo_visibility_attempts": attempts,
            "algo_transient_errors": transient_errors,
        }
        if evidence["terminal_queries"]["KNOWN_ORDINARY"] != "CANCELED":
            errors.append("RESTART_ORDINARY_TERMINAL_NOT_CANCELED")
        if evidence["terminal_queries"]["KNOWN_ALGO"] != "CANCELED":
            errors.append("RESTART_ALGO_TERMINAL_NOT_CANCELED")
        if evidence["terminal_queries"]["UNKNOWN_SENTINEL"] != "CANCELED":
            errors.append("SENTINEL_CLEANUP_TERMINAL_NOT_CANCELED")

        postflight = await _responsibility_snapshot(account_api)
        evidence["restart_postflight"] = postflight
        evidence["responsibility_cleared"] = _all_clear(postflight)
        if not evidence["responsibility_cleared"]:
            errors.append("RESTART_POSTFLIGHT_RESPONSIBILITY_NOT_CLEAR")
    finally:
        await node.stop_async()


def _run_node_phase(
    phase_name: str,
    strategy,
    observer,
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
    evidence: dict[str, object],
    errors: list[str],
) -> None:
    lifecycle = {
        "built": False,
        "stopped": False,
        "public_kernel_tasks_cleared": False,
        "pending_tasks_after_public_cleanup": None,
        "disposed": False,
    }
    loop: asyncio.AbstractEventLoop | None = None
    node: TradingNode | None = None
    try:
        node_config, _provider_config, data_config, exec_config = _build_configuration(
            api_key,
            api_secret,
            proxy_url,
        )
        if exec_config.max_retries is not None:
            raise QualificationError("EXEC_WRITE_RETRIES_NOT_DISABLED")
        if data_config.proxy_url != proxy_url or exec_config.proxy_url != proxy_url:
            raise QualificationError("CLIENT_PROXY_CONFIGURATION_MISMATCH")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        node = TradingNode(config=node_config, loop=loop)
        node.add_data_client_factory(BINANCE, BinanceLiveDataClientFactory)
        node.add_exec_client_factory(BINANCE, BinanceLiveExecClientFactory)
        node.build()
        lifecycle["built"] = node.is_built()
        node.trader.add_strategy(strategy)
        observer_task = loop.create_task(observer(node, strategy))
        node.run(raise_exception=True)
        if observer_task.done():
            observer_task.result()
        else:
            errors.append(f"{phase_name}_OBSERVER_TASK_NOT_COMPLETED")
            observer_task.cancel()
    except Exception as exc:
        if isinstance(exc, QualificationError):
            errors.append(f"{phase_name}_FAILED:{exc}")
        else:
            errors.append(f"{phase_name}_FAILED:{type(exc).__name__}")
    finally:
        if node is not None:
            try:
                if node.is_running():
                    node.stop()
                lifecycle["stopped"] = not node.is_running()
            except Exception as exc:
                errors.append(f"{phase_name}_NODE_STOP_FAILED:{type(exc).__name__}")
            try:
                # Nautilus 1.230.0 registers a long-lived ActorExecutor worker for every
                # strategy. TradingNode.dispose() closes a stopped loop without awaiting
                # that worker, while this documented kernel lifecycle method cancels and
                # awaits all remaining loop tasks before disposal.
                if not node.kernel.loop.is_closed():
                    node.kernel.cancel_all_tasks()
                    pending_tasks = [
                        task
                        for task in asyncio.all_tasks(node.kernel.loop)
                        if not task.done()
                    ]
                    lifecycle["pending_tasks_after_public_cleanup"] = len(pending_tasks)
                    lifecycle["public_kernel_tasks_cleared"] = not pending_tasks
                    if pending_tasks:
                        errors.append(f"{phase_name}_PUBLIC_KERNEL_TASK_CLEANUP_INCOMPLETE")
            except Exception as exc:
                errors.append(f"{phase_name}_PUBLIC_KERNEL_TASK_CLEANUP_FAILED:{type(exc).__name__}")
            try:
                node.dispose()
                lifecycle["disposed"] = True
            except Exception as exc:
                errors.append(f"{phase_name}_NODE_DISPOSE_FAILED:{type(exc).__name__}")
        asyncio.set_event_loop(None)
        if loop is not None and not loop.is_closed():
            loop.close()
        get_cached_binance_futures_instrument_provider.cache_clear()
        get_cached_binance_http_client.cache_clear()
        evidence.setdefault("node_lifecycles", {})[phase_name] = lifecycle


async def _emergency_cleanup(
    identities: dict[str, str],
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
) -> dict[str, object]:
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
    ordinary = await account_api.query_open_orders(symbol="BTCUSDT", recv_window="5000")
    algo = await account_api.query_open_algo_orders(symbol="BTCUSDT", recv_window="5000")
    own_ordinary_ids = {
        client_order_id
        for profile, client_order_id in identities.items()
        if profile != "KNOWN_ALGO"
    }
    ordinary_canceled = 0
    algo_canceled = 0
    for order in ordinary:
        if order.clientOrderId in own_ordinary_ids:
            await account_api.cancel_order(
                symbol="BTCUSDT",
                order_id=order.orderId,
                orig_client_order_id=None,
                recv_window="5000",
            )
            ordinary_canceled += 1
    for order in algo:
        if order.clientAlgoId == identities.get("KNOWN_ALGO"):
            await account_api.cancel_algo_order(
                algo_id=order.algoId,
                client_algo_id=None,
                recv_window="5000",
            )
            algo_canceled += 1
    postflight = await _responsibility_snapshot(account_api)
    return {
        "ordinary_orders_canceled": ordinary_canceled,
        "algo_orders_canceled": algo_canceled,
        "used_fixed_package_account_wrapper": bool(ordinary_canceled or algo_canceled),
        "responsibility_cleared": _all_clear(postflight),
        "actual_client_order_ids_persisted": False,
    }


def _run(evidence_path: Path | None, proxy_url: str | None) -> int:
    evidence: dict[str, object] = {
        "stage": "B00_ORDINARY_AND_ALGO_RESTART_RECOVERY",
        "profile": "BINANCE_DEMO",
        "scope": "B00_ISOLATED_QUALIFICATION_ONLY",
        "actual_client_order_ids_persisted": False,
        "persistent_cache": False,
        "external_order_claims": None,
        "proxy": "RUNTIME_LOOPBACK_ARGUMENT" if proxy_url is not None else "DISABLED",
    }
    errors: list[str] = []
    identities: dict[str, str] = {}
    mutex = None
    api_key: str | None = None
    api_secret: str | None = None
    try:
        proxy_url = _validate_proxy_url(proxy_url)
        mutex = _acquire_executor_mutex()
        evidence["executor_mutex"] = "ACQUIRED_CURRENT_USER_PROTECTED_DACL"
        api_key, api_secret, backend_name = _load_credentials()
        evidence["credential_backend"] = backend_name
        LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
        with _without_binance_credential_environment() as environment_was_populated:
            evidence["credential_environment_sanitized"] = True
            evidence["credential_environment_had_values"] = environment_was_populated
            seed_strategy = DemoRestartSeedStrategy(
                config=StrategyConfig(
                    strategy_id="B00SEED",
                    order_id_tag="001",
                    external_order_claims=None,
                    manage_contingent_orders=False,
                    manage_gtd_expiry=False,
                    manage_stop=False,
                ),
            )
            _run_node_phase(
                "SEED",
                seed_strategy,
                lambda node, strategy: _seed_phase(
                    node,
                    strategy,
                    api_key,
                    api_secret,
                    proxy_url,
                    identities,
                    evidence,
                    errors,
                ),
                api_key,
                api_secret,
                proxy_url,
                evidence,
                errors,
            )
            if set(identities) == EXPECTED_PROFILES:
                recovery_strategy = DemoExternalOrderRecoveryStrategy(
                    config=StrategyConfig(
                        strategy_id="B00RECOVER",
                        order_id_tag="001",
                        external_order_claims=None,
                        manage_contingent_orders=False,
                        manage_gtd_expiry=False,
                        manage_stop=False,
                    ),
                )
                _run_node_phase(
                    "RECOVERY",
                    recovery_strategy,
                    lambda node, strategy: _recovery_phase(
                        node,
                        strategy,
                        api_key,
                        api_secret,
                        proxy_url,
                        identities,
                        evidence,
                        errors,
                    ),
                    api_key,
                    api_secret,
                    proxy_url,
                    evidence,
                    errors,
                )
            elif not identities:
                errors.append("NO_SEEDED_IDENTITY_AVAILABLE_FOR_RECOVERY")
    except Exception as exc:
        if isinstance(exc, QualificationError):
            errors.append(f"RESTART_RECOVERY_PROBE_FAILED:{exc}")
        else:
            errors.append(f"RESTART_RECOVERY_PROBE_FAILED:{type(exc).__name__}")
    finally:
        if identities and not evidence.get("responsibility_cleared") and api_key and api_secret:
            try:
                emergency = asyncio.run(
                    _emergency_cleanup(identities, api_key, api_secret, proxy_url),
                )
                evidence["emergency_cleanup"] = emergency
                if emergency["used_fixed_package_account_wrapper"]:
                    errors.append("EMERGENCY_CLEANUP_REQUIRED")
                evidence["responsibility_cleared"] = emergency["responsibility_cleared"]
            except Exception as exc:
                errors.append(f"EMERGENCY_CLEANUP_FAILED:{type(exc).__name__}")
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

    evidence["errors"] = sorted(set(errors))
    if evidence.get("responsibility_cleared") and not errors:
        evidence["status"] = "QUALIFIED"
    elif evidence.get("responsibility_cleared"):
        evidence["status"] = "RESPONSIBILITY_CLEARED_QUALIFICATION_REJECTED"
    else:
        evidence["status"] = "RECOVERY_FAILED"

    rendered = _canonical_json(evidence)
    if any(client_order_id in rendered for client_order_id in identities.values()):
        evidence = {"status": "RECOVERY_FAILED", "errors": ["EVIDENCE_IDENTITY_LEAK_GUARD"]}
    elif api_key is not None and api_key in rendered:
        evidence = {"status": "RECOVERY_FAILED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    elif api_secret is not None and api_secret in rendered:
        evidence = {"status": "RECOVERY_FAILED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    _write_evidence(evidence_path, evidence)
    return 0 if evidence.get("status") == "QUALIFIED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qualify ordinary/algo restart query-cancel and unknown isolation on Demo.",
    )
    parser.add_argument("--evidence-path", type=Path)
    parser.add_argument("--proxy-url")
    args = parser.parse_args()
    return _run(args.evidence_path, args.proxy_url)


if __name__ == "__main__":
    raise SystemExit(main())
