from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import get_cached_binance_http_client
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.common.enums import BinanceFuturesPositionSide
from nautilus_trader.adapters.binance.common.enums import BinanceKeyType
from nautilus_trader.adapters.binance.common.enums import BinanceOrderSide
from nautilus_trader.adapters.binance.common.enums import BinanceOrderType
from nautilus_trader.adapters.binance.factories import (
    get_cached_binance_futures_instrument_provider,
)
from nautilus_trader.adapters.binance.futures.http.account import (
    BinanceFuturesAccountHttpAPI,
)
from nautilus_trader.common.component import LiveClock
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.config import StrategyConfig

from tools.qualification.nautilus_fixtures import DemoReduceOnlyTopologyStrategy
from tools.qualification.probe_binance_demo_clients import LOG_DIRECTORY
from tools.qualification.probe_binance_demo_clients import QualificationError
from tools.qualification.probe_binance_demo_clients import _acquire_executor_mutex
from tools.qualification.probe_binance_demo_clients import _canonical_json
from tools.qualification.probe_binance_demo_clients import _load_credentials
from tools.qualification.probe_binance_demo_clients import _release_executor_mutex
from tools.qualification.probe_binance_demo_clients import _scan_paths_for_credentials
from tools.qualification.probe_binance_demo_clients import _validate_proxy_url
from tools.qualification.probe_binance_demo_clients import _without_binance_credential_environment
from tools.qualification.probe_binance_demo_clients import _write_evidence
from tools.qualification.probe_binance_demo_order_roundtrip import _all_clear
from tools.qualification.probe_binance_demo_order_roundtrip import _responsibility_snapshot
from tools.qualification.probe_binance_demo_reduce_only_topology import _account_api
from tools.qualification.probe_binance_demo_reduce_only_topology import _position_amount
from tools.qualification.probe_binance_demo_reduce_only_topology import _sample_flat_position
from tools.qualification.probe_binance_demo_reduce_only_topology import (
    _wait_for_all_algos_open,
)
from tools.qualification.probe_binance_demo_reduce_only_topology import (
    _wait_for_node_ready,
)
from tools.qualification.probe_binance_demo_reduce_only_topology import _wait_for_owned_algos_clear
from tools.qualification.probe_binance_demo_reduce_only_topology import _wait_for_position
from tools.qualification.probe_binance_demo_restart_recovery import _run_node_phase


SYMBOL = "BTCUSDT"
QUANTITY = Decimal("0.002")


def _tags(order) -> set[str]:
    return set(order.tags or [])


async def _seed_position(
    node: TradingNode,
    strategy: DemoReduceOnlyTopologyStrategy,
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

        for _ in range(200):
            if strategy.last_bid is not None:
                break
            await asyncio.sleep(0.05)
        if strategy.last_bid is None:
            errors.append("SEED_QUOTE_NOT_AVAILABLE")
            return

        strategy.submit_entry_market("SEED_ENTRY", format(QUANTITY, "f"))
        position = await _wait_for_position(account_api, QUANTITY)
        if position != QUANTITY:
            errors.append("SEED_POSITION_NOT_OBSERVED")
            return
        fill_observed_ns = node.kernel.clock.timestamp_ns()
        strategy.submit_protective_stop(
            "SEED_STOP",
            format(QUANTITY, "f"),
            float(strategy.last_bid) * 0.8,
        )
        visible = await _wait_for_all_algos_open(
            account_api,
            strategy,
            ("SEED_STOP",),
        )
        protection_observed_ns = node.kernel.clock.timestamp_ns()
        if set(visible) != {"SEED_STOP"}:
            errors.append("SEED_PROTECTION_NOT_OPEN")
            return

        identities.update(
            {
                profile: strategy.orders[profile].client_order_id.value
                for profile in ("SEED_ENTRY", "SEED_STOP")
            },
        )
        protection_latency_seconds = (
            protection_observed_ns - fill_observed_ns
        ) / 1_000_000_000
        evidence["seed"] = {
            "position_quantity": format(position, "f"),
            "protection_quantity": visible["SEED_STOP"].quantity,
            "protection_reduce_only": visible["SEED_STOP"].reduceOnly,
            "protection_close_position": visible["SEED_STOP"].closePosition,
            "protection_latency_seconds": protection_latency_seconds,
            "protection_within_30_seconds": protection_latency_seconds <= 30,
            "identity_profiles_in_memory": sorted(identities),
            "actual_client_order_ids_persisted": False,
            "persistent_cache": False,
        }
        if not evidence["seed"]["protection_within_30_seconds"]:
            errors.append("SEED_PROTECTION_DEADLINE_EXCEEDED")
        if strategy.errors:
            errors.extend(strategy.errors)
    finally:
        await node.stop_async()


async def _wait_for_recovered_cache(
    node: TradingNode,
    identities: dict[str, str],
) -> tuple[object | None, object | None, list[object], list[object], int]:
    entry_order = None
    stop_order = None
    positions: list[object] = []
    orders: list[object] = []
    attempts = 0
    for attempts in range(1, 151):
        entry_order = node.cache.order(ClientOrderId(identities["SEED_ENTRY"]))
        stop_order = node.cache.order(ClientOrderId(identities["SEED_STOP"]))
        positions = list(
            node.cache.positions_open(
                instrument_id=InstrumentId.from_str("BTCUSDT-PERP.BINANCE"),
            ),
        )
        orders = list(node.cache.orders())
        if entry_order is not None and stop_order is not None and positions:
            break
        await asyncio.sleep(0.1)
    return entry_order, stop_order, positions, orders, attempts


async def _recover_and_exit(
    node: TradingNode,
    strategy: DemoReduceOnlyTopologyStrategy,
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
        startup_position = await _position_amount(account_api)
        startup_algos = await account_api.query_open_algo_orders(
            symbol=SYMBOL,
            recv_window="5000",
        )
        own_startup_algos = [
            order
            for order in startup_algos
            if order.clientAlgoId == identities["SEED_STOP"]
        ]
        if startup_position != QUANTITY or len(own_startup_algos) != 1:
            errors.append("RECOVERY_STARTUP_VENUE_RESPONSIBILITY_MISMATCH")
            return

        entry_order, stop_order, positions, orders, cache_attempts = (
            await _wait_for_recovered_cache(node, identities)
        )
        relevant_positions = [
            position
            for position in positions
            if str(position.instrument_id) == "BTCUSDT-PERP.BINANCE"
        ]
        projection_orders = [
            order
            for order in orders
            if _tags(order) & {"VENUE", "RECONCILIATION"}
        ]
        evidence["generated_technical_cache"] = {
            "cache_wait_attempts": cache_attempts,
            "seed_entry_found_by_original_uuid32": entry_order is not None,
            "seed_stop_found_by_original_uuid32": stop_order is not None,
            "open_position_count": len(relevant_positions),
            "open_position_quantities": [
                format(position.signed_decimal_qty(), "f")
                for position in relevant_positions
            ],
            "technical_projection_order_count": len(projection_orders),
            "technical_projection_tags": sorted(
                {tag for order in projection_orders for tag in _tags(order)}
            ),
            "entry_technical_strategy_id": (
                None if entry_order is None else str(entry_order.strategy_id)
            ),
            "stop_technical_strategy_id": (
                None if stop_order is None else str(stop_order.strategy_id)
            ),
            "persistent_cache": False,
            "projection_is_product_fact": False,
            "projection_can_trigger_product_action": False,
            "actual_client_order_ids_persisted": False,
        }
        if entry_order is None:
            errors.append("RECOVERED_ENTRY_ORDER_MISSING")
        if stop_order is None:
            errors.append("RECOVERED_STOP_ORDER_MISSING")
        if not relevant_positions:
            errors.append("RECOVERED_POSITION_MISSING")
        if not projection_orders:
            errors.append("RECOVERY_TECHNICAL_PROJECTION_MISSING")
        if errors:
            return

        await asyncio.sleep(0.5)
        passive_position = await _position_amount(account_api)
        passive_algos = await account_api.query_open_algo_orders(
            symbol=SYMBOL,
            recv_window="5000",
        )
        passive_stop_present = any(
            order.clientAlgoId == identities["SEED_STOP"]
            for order in passive_algos
        )
        evidence["passive_reconciliation"] = {
            "position_unchanged_before_explicit_action": passive_position == QUANTITY,
            "protective_stop_unchanged_before_explicit_action": passive_stop_present,
            "automatic_exit_triggered": False,
        }
        if passive_position != QUANTITY or not passive_stop_present:
            errors.append("RECONCILIATION_PROJECTION_CHANGED_VENUE_RESPONSIBILITY")
            return

        strategy.adopt_reconciled_order("RECOVERED_STOP", stop_order)
        strategy.query_profile("RECOVERED_STOP")
        strategy.submit_reduce_only_market("RECOVERY_EXIT", format(QUANTITY, "f"))
        flat_position = await _wait_for_position(account_api, Decimal("0"))
        exit_order = strategy.orders["RECOVERY_EXIT"]
        venue_exit = None
        for _ in range(20):
            venue_exit = await account_api.query_order(
                symbol=SYMBOL,
                orig_client_order_id=exit_order.client_order_id.value,
                recv_window="5000",
            )
            if venue_exit is not None and venue_exit.status.value == "FILLED":
                break
            await asyncio.sleep(0.25)
        evidence["risk_engine_reduce_only_exit"] = {
            "requested_quantity": format(QUANTITY, "f"),
            "recovered_position_quantity": format(startup_position, "f"),
            "request_not_above_recovered_position": QUANTITY <= startup_position,
            "risk_engine_denied": any(
                error.startswith("ORDER_DENIED:RECOVERY_EXIT")
                for error in strategy.errors
            ),
            "reduce_only": exit_order.is_reduce_only,
            "venue_status": None if venue_exit is None else venue_exit.status.value,
            "position_after_exit": format(flat_position, "f"),
            "write_retried": False,
        }
        if flat_position != 0:
            errors.append("RECOVERY_REDUCE_ONLY_EXIT_DID_NOT_FLATTEN")
        if evidence["risk_engine_reduce_only_exit"]["risk_engine_denied"]:
            errors.append("RISK_ENGINE_DENIED_RECOVERY_EXIT")
        if not exit_order.is_reduce_only:
            errors.append("RECOVERY_EXIT_NOT_REDUCE_ONLY")
        if venue_exit is None or venue_exit.status.value != "FILLED":
            errors.append("RECOVERY_EXIT_TERMINAL_NOT_FILLED")

        strategy.cancel_profile("RECOVERED_STOP")
        remaining = await _wait_for_owned_algos_clear(
            account_api,
            strategy,
            ("RECOVERED_STOP",),
        )
        no_reverse_samples = await _sample_flat_position(account_api)
        evidence["recovered_protection_cleanup"] = {
            "public_query_calls": list(strategy.public_query_calls),
            "public_cancel_calls": list(strategy.public_cancel_calls),
            "remaining_profiles": sorted(remaining),
            "no_reverse_samples": no_reverse_samples,
            "all_samples_flat": all(
                Decimal(value) == 0 for value in no_reverse_samples
            ),
        }
        if remaining:
            errors.append("RECOVERED_PROTECTION_NOT_CLEARED")
        if not evidence["recovered_protection_cleanup"]["all_samples_flat"]:
            errors.append("RECOVERY_EXIT_REVERSED_POSITION")
        if strategy.errors:
            errors.extend(strategy.errors)

        postflight = await _responsibility_snapshot(account_api)
        evidence["recovery_postflight"] = postflight
        evidence["responsibility_cleared"] = _all_clear(postflight)
        if not evidence["responsibility_cleared"]:
            errors.append("RECOVERY_POSTFLIGHT_RESPONSIBILITY_NOT_CLEAR")
    finally:
        await node.stop_async()


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
    position = await _position_amount(account_api)
    market_exit_required = False
    if position != 0:
        await account_api.new_order(
            symbol=SYMBOL,
            side=BinanceOrderSide.SELL if position > 0 else BinanceOrderSide.BUY,
            order_type=BinanceOrderType.MARKET,
            position_side=BinanceFuturesPositionSide.BOTH,
            quantity=format(abs(position), "f"),
            reduce_only="true",
            new_client_order_id=uuid4().hex,
            recv_window="5000",
        )
        market_exit_required = True

    algo_cancel_required = False
    algo_orders = await account_api.query_open_algo_orders(
        symbol=SYMBOL,
        recv_window="5000",
    )
    for order in algo_orders:
        if order.clientAlgoId == identities.get("SEED_STOP"):
            await account_api.cancel_algo_order(
                algo_id=order.algoId,
                client_algo_id=None,
                recv_window="5000",
            )
            algo_cancel_required = True
    await asyncio.sleep(0.25)
    postflight = await _responsibility_snapshot(account_api)
    return {
        "fixed_package_market_exit_required": market_exit_required,
        "fixed_package_algo_cancel_required": algo_cancel_required,
        "responsibility_cleared": _all_clear(postflight),
        "actual_client_order_ids_persisted": False,
    }


def _run(evidence_path: Path | None, proxy_url: str | None) -> int:
    evidence: dict[str, object] = {
        "operation": "DIRECT_GENERATE_MISSING_ORDERS_POSITION_RECOVERY",
        "profile": "BINANCE_DEMO",
        "scope": "DIRECT_ISOLATED_QUALIFICATION_ONLY",
        "generate_missing_orders": True,
        "persistent_cache": False,
        "actual_client_order_ids_persisted": False,
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
            seed_strategy = DemoReduceOnlyTopologyStrategy(
                config=StrategyConfig(
                    strategy_id="DIRECTMISSSEED",
                    order_id_tag="001",
                    external_order_claims=None,
                    manage_contingent_orders=False,
                    manage_gtd_expiry=False,
                    manage_stop=False,
                ),
            )
            error_count_before_seed = len(errors)
            _run_node_phase(
                "MISSING_POSITION_SEED",
                seed_strategy,
                lambda node, strategy: _seed_position(
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
            seed_succeeded = (
                len(errors) == error_count_before_seed
                and set(identities) == {"SEED_ENTRY", "SEED_STOP"}
                and evidence.get("seed", {}).get("protection_within_30_seconds") is True
            )
            if seed_succeeded:
                recovery_strategy = DemoReduceOnlyTopologyStrategy(
                    config=StrategyConfig(
                        strategy_id="DIRECTMISSREC",
                        order_id_tag="001",
                        external_order_claims=None,
                        manage_contingent_orders=False,
                        manage_gtd_expiry=False,
                        manage_stop=False,
                    ),
                )
                _run_node_phase(
                    "MISSING_POSITION_RECOVERY",
                    recovery_strategy,
                    lambda node, strategy: _recover_and_exit(
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
            else:
                errors.append("SEED_NOT_SAFE_FOR_RECOVERY_PHASE")
    except Exception as exc:
        if isinstance(exc, QualificationError):
            errors.append(f"MISSING_POSITION_PROBE_FAILED:{exc}")
        else:
            errors.append(f"MISSING_POSITION_PROBE_FAILED:{type(exc).__name__}")
    finally:
        if identities and not evidence.get("responsibility_cleared") and api_key and api_secret:
            try:
                emergency = asyncio.run(
                    _emergency_cleanup(identities, api_key, api_secret, proxy_url),
                )
                evidence["emergency_cleanup"] = emergency
                evidence["responsibility_cleared"] = emergency["responsibility_cleared"]
                if (
                    emergency["fixed_package_market_exit_required"]
                    or emergency["fixed_package_algo_cancel_required"]
                ):
                    errors.append("FIXED_PACKAGE_EMERGENCY_WRITE_REQUIRED")
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
        evidence["status"] = "RESPONSIBILITY_NOT_CLEARED"

    rendered = _canonical_json(evidence)
    if any(identity in rendered for identity in identities.values()):
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_IDENTITY_LEAK_GUARD"]}
    elif api_key is not None and api_key in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    elif api_secret is not None and api_secret in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    _write_evidence(evidence_path, evidence)
    return 0 if evidence.get("status") == "QUALIFIED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qualify generate_missing_orders position recovery on Binance Demo.",
    )
    parser.add_argument("--evidence-path", type=Path)
    parser.add_argument("--proxy-url")
    args = parser.parse_args()
    return _run(args.evidence_path, args.proxy_url)


if __name__ == "__main__":
    raise SystemExit(main())
