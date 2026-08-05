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

from nautilus_trader.adapters.binance import BINANCE
from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import BinanceLiveDataClientFactory
from nautilus_trader.adapters.binance import BinanceLiveExecClientFactory
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
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.trading.config import StrategyConfig

from tools.qualification.nautilus_fixtures import DemoReduceOnlyTopologyStrategy
from tools.qualification.probe_binance_demo_clients import INSTRUMENT_IDS
from tools.qualification.probe_binance_demo_clients import INSTRUMENT_SYMBOLS
from tools.qualification.probe_binance_demo_clients import LOG_DIRECTORY
from tools.qualification.probe_binance_demo_clients import QualificationError
from tools.qualification.probe_binance_demo_clients import _acquire_executor_mutex
from tools.qualification.probe_binance_demo_clients import _build_configuration
from tools.qualification.probe_binance_demo_clients import _canonical_json
from tools.qualification.probe_binance_demo_clients import _effective_leverage
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


SYMBOL = "BTCUSDT"
ENTRY_INCREMENT = Decimal("0.002")
TOTAL_POSITION = Decimal("0.004")
ALGO_PROFILES = ("STOP_A", "STOP_B", "TP2", "TP1")


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


async def _position_amount(account_api: BinanceFuturesAccountHttpAPI) -> Decimal:
    positions = await account_api.query_futures_position_risk(
        symbol=SYMBOL,
        recv_window="5000",
    )
    return sum(
        (Decimal(position.positionAmt) for position in positions),
        start=Decimal("0"),
    )


async def _wait_for_position(
    account_api: BinanceFuturesAccountHttpAPI,
    expected: Decimal,
    *,
    attempts: int = 120,
    delay_seconds: float = 0.1,
) -> Decimal:
    actual = await _position_amount(account_api)
    for _ in range(attempts):
        if actual == expected:
            return actual
        await asyncio.sleep(delay_seconds)
        actual = await _position_amount(account_api)
    return actual


async def _owned_open_algos(
    account_api: BinanceFuturesAccountHttpAPI,
    strategy: DemoReduceOnlyTopologyStrategy,
    profiles: tuple[str, ...] = ALGO_PROFILES,
) -> dict[str, object]:
    identities = {
        profile: strategy.orders[profile].client_order_id.value
        for profile in profiles
        if profile in strategy.orders
    }
    venue_orders = await account_api.query_open_algo_orders(
        symbol=SYMBOL,
        recv_window="5000",
    )
    by_identity = {order.clientAlgoId: order for order in venue_orders}
    return {
        profile: by_identity[identity]
        for profile, identity in identities.items()
        if identity in by_identity
    }


async def _wait_for_all_algos_open(
    account_api: BinanceFuturesAccountHttpAPI,
    strategy: DemoReduceOnlyTopologyStrategy,
    profiles: tuple[str, ...] = ALGO_PROFILES,
) -> dict[str, object]:
    visible: dict[str, object] = {}
    for _ in range(120):
        visible = await _owned_open_algos(account_api, strategy, profiles)
        if set(visible) == set(profiles):
            return visible
        if strategy.errors:
            return visible
        await asyncio.sleep(0.1)
    return visible


async def _wait_for_owned_algos_clear(
    account_api: BinanceFuturesAccountHttpAPI,
    strategy: DemoReduceOnlyTopologyStrategy,
    profiles: tuple[str, ...] = ALGO_PROFILES,
) -> dict[str, object]:
    visible: dict[str, object] = {}
    for _ in range(120):
        visible = await _owned_open_algos(account_api, strategy, profiles)
        if not visible:
            return visible
        await asyncio.sleep(0.1)
    return visible


def _algo_topology_evidence(
    visible: dict[str, object],
    strategy: DemoReduceOnlyTopologyStrategy,
) -> dict[str, dict[str, object]]:
    return {
        profile: {
            "same_uuid32_round_trip": (
                venue.clientAlgoId == strategy.orders[profile].client_order_id.value
            ),
            "order_type": venue.orderType,
            "quantity": venue.quantity,
            "quantity_is_explicit": venue.quantity is not None,
            "reduce_only": venue.reduceOnly,
            "close_position": venue.closePosition,
            "working_type": venue.workingType,
            "status": venue.algoStatus,
        }
        for profile, venue in visible.items()
    }


async def _sample_flat_position(
    account_api: BinanceFuturesAccountHttpAPI,
    *,
    samples: int = 8,
) -> list[str]:
    values: list[str] = []
    for _ in range(samples):
        await asyncio.sleep(0.25)
        values.append(format(await _position_amount(account_api), "f"))
    return values


async def _current_algo_status(
    account_api: BinanceFuturesAccountHttpAPI,
    strategy: DemoReduceOnlyTopologyStrategy,
    profile: str,
) -> tuple[str | None, int, int]:
    venue, attempts, transient_errors = await _query_algo_order_until_visible(
        account_api,
        strategy.orders[profile].client_order_id.value,
        max_attempts=20,
        delay_seconds=0.25,
    )
    return (
        None if venue is None else venue.algoStatus,
        attempts,
        transient_errors,
    )


async def _wait_for_terminal_algo_status(
    account_api: BinanceFuturesAccountHttpAPI,
    strategy: DemoReduceOnlyTopologyStrategy,
    profile: str,
    *,
    max_attempts: int = 20,
    delay_seconds: float = 0.25,
) -> tuple[str | None, int, int]:
    terminal_statuses = {"CANCELED", "EXPIRED", "FINISHED", "REJECTED"}
    status: str | None = None
    total_transient_errors = 0
    for attempt in range(1, max_attempts + 1):
        status, _visibility_attempts, transient_errors = await _current_algo_status(
            account_api,
            strategy,
            profile,
        )
        total_transient_errors += transient_errors
        if status in terminal_statuses:
            return status, attempt, total_transient_errors
        if attempt < max_attempts:
            await asyncio.sleep(delay_seconds)
    return status, max_attempts, total_transient_errors


async def _run_partial_tp_episode(
    node: TradingNode,
    account_api: BinanceFuturesAccountHttpAPI,
    strategy: DemoReduceOnlyTopologyStrategy,
    evidence: dict[str, object],
    errors: list[str],
) -> None:
    profiles = ("PARTIAL_STOP", "TP_PARTIAL", "TP_REMAINDER")
    strategy.submit_entry_market("PARTIAL_ENTRY", format(TOTAL_POSITION, "f"))
    position = await _wait_for_position(account_api, TOTAL_POSITION)
    if position != TOTAL_POSITION:
        errors.append("PARTIAL_EPISODE_ENTRY_NOT_OBSERVED")
        return

    instrument = node.cache.instrument(strategy.instrument_id)
    if instrument is None or strategy.last_bid is None or strategy.last_ask is None:
        errors.append("PARTIAL_EPISODE_REFERENCE_NOT_AVAILABLE")
        return
    tick = float(instrument.price_increment)
    strategy.submit_protective_stop(
        "PARTIAL_STOP",
        format(TOTAL_POSITION, "f"),
        float(strategy.last_bid) * 0.8,
    )
    stop_visible = await _wait_for_all_algos_open(
        account_api,
        strategy,
        ("PARTIAL_STOP",),
    )
    if set(stop_visible) != {"PARTIAL_STOP"}:
        errors.append("PARTIAL_EPISODE_STOP_NOT_OPEN_BEFORE_TP")
        return

    # This episode intentionally submits TP1 before TP2, opposite to the stable
    # topology episode. The near trigger exits half the venue position.
    strategy.submit_take_profit(
        "TP_PARTIAL",
        format(ENTRY_INCREMENT, "f"),
        float(strategy.last_ask) + (2 * tick),
    )
    strategy.submit_take_profit(
        "TP_REMAINDER",
        format(ENTRY_INCREMENT, "f"),
        float(strategy.last_ask) * 1.2,
    )
    initially_visible = await _wait_for_all_algos_open(account_api, strategy, profiles)
    partial_position = await _wait_for_position(
        account_api,
        ENTRY_INCREMENT,
        attempts=120,
        delay_seconds=0.5,
    )
    tp_status, attempts, transient_errors = await _wait_for_terminal_algo_status(
        account_api,
        strategy,
        "TP_PARTIAL",
    )
    remaining_open = await _owned_open_algos(account_api, strategy, profiles)
    evidence["tp_partial_position_exit"] = {
        "submission_order": [
            profile
            for profile in strategy.submitted
            if profile in {"PARTIAL_ENTRY", *profiles}
        ],
        "starting_position": format(TOTAL_POSITION, "f"),
        "tp_explicit_quantity": format(ENTRY_INCREMENT, "f"),
        "position_after_tp": format(partial_position, "f"),
        "all_stop_and_tp_profiles_open_before_trigger": set(initially_visible) == set(profiles),
        "stop_and_tp2_still_open_after_partial_exit": (
            {"PARTIAL_STOP", "TP_REMAINDER"} <= set(remaining_open)
        ),
        "tp_terminal_status": tp_status,
        "tp_query_attempts": attempts,
        "tp_query_transient_errors": transient_errors,
        "same_uuid32_read_retry_only": True,
        "write_retried": False,
    }
    if partial_position != ENTRY_INCREMENT:
        errors.append("TP_PARTIAL_POSITION_EXIT_NOT_OBSERVED")
        if partial_position > 0:
            strategy.submit_reduce_only_market(
                "PARTIAL_TIMEOUT_EXIT",
                format(partial_position, "f"),
            )
            await _wait_for_position(account_api, Decimal("0"))
        for profile in profiles:
            strategy.cancel_profile(profile)
        await _wait_for_owned_algos_clear(account_api, strategy, profiles)
        return
    if tp_status != "FINISHED":
        errors.append("TP_PARTIAL_TERMINAL_NOT_FINISHED")
    if not {"PARTIAL_STOP", "TP_REMAINDER"} <= set(remaining_open):
        errors.append("PARTIAL_EXIT_SIBLING_TOPOLOGY_NOT_OPEN")

    strategy.submit_reduce_only_market(
        "PARTIAL_REMAINDER_EXIT",
        format(ENTRY_INCREMENT, "f"),
    )
    flat_position = await _wait_for_position(account_api, Decimal("0"))
    no_reverse_samples = await _sample_flat_position(account_api)
    evidence["partial_episode_remainder_exit"] = {
        "position_after_exit": format(flat_position, "f"),
        "no_reverse_samples": no_reverse_samples,
        "all_flat": flat_position == 0
        and all(Decimal(value) == 0 for value in no_reverse_samples),
    }
    if not evidence["partial_episode_remainder_exit"]["all_flat"]:
        errors.append("PARTIAL_EPISODE_REMAINDER_EXIT_NOT_FLAT")

    for profile in profiles:
        strategy.cancel_profile(profile)
    remaining = await _wait_for_owned_algos_clear(account_api, strategy, profiles)
    evidence["partial_episode_sibling_cleanup"] = {
        "remaining_owned_algo_profiles": sorted(remaining),
    }
    if remaining:
        errors.append("PARTIAL_EPISODE_SIBLINGS_NOT_CLEARED")


async def _run_stop_tp_race_episode(
    node: TradingNode,
    account_api: BinanceFuturesAccountHttpAPI,
    strategy: DemoReduceOnlyTopologyStrategy,
    evidence: dict[str, object],
    errors: list[str],
) -> None:
    profiles = ("RACE_STOP", "RACE_TP")
    strategy.submit_entry_market("RACE_ENTRY", format(ENTRY_INCREMENT, "f"))
    position = await _wait_for_position(account_api, ENTRY_INCREMENT)
    if position != ENTRY_INCREMENT:
        errors.append("RACE_EPISODE_ENTRY_NOT_OBSERVED")
        return

    instrument = node.cache.instrument(strategy.instrument_id)
    if instrument is None or strategy.last_bid is None or strategy.last_ask is None:
        errors.append("RACE_EPISODE_REFERENCE_NOT_AVAILABLE")
        return
    tick = float(instrument.price_increment)
    strategy.submit_protective_stop(
        "RACE_STOP",
        format(ENTRY_INCREMENT, "f"),
        float(strategy.last_bid) - (100 * tick),
    )
    strategy.submit_take_profit(
        "RACE_TP",
        format(ENTRY_INCREMENT, "f"),
        float(strategy.last_ask) + (100 * tick),
    )
    initially_visible = await _wait_for_all_algos_open(account_api, strategy, profiles)
    race_position = await _wait_for_position(
        account_api,
        Decimal("0"),
        attempts=180,
        delay_seconds=0.5,
    )
    timed_out = race_position != 0
    if timed_out:
        errors.append("STOP_TP_RACE_TRIGGER_TIMEOUT")
        strategy.submit_reduce_only_market(
            "RACE_TIMEOUT_EXIT",
            format(abs(race_position), "f"),
            OrderSide.SELL if race_position > 0 else OrderSide.BUY,
        )
        race_position = await _wait_for_position(account_api, Decimal("0"))

    no_reverse_samples = await _sample_flat_position(account_api, samples=12)
    pre_cleanup_statuses = {}
    for profile in profiles:
        status, attempts, transient_errors = await _current_algo_status(
            account_api,
            strategy,
            profile,
        )
        pre_cleanup_statuses[profile] = {
            "status": status,
            "query_attempts": attempts,
            "query_transient_errors": transient_errors,
        }

    for profile in profiles:
        strategy.cancel_profile(profile)
    remaining = await _wait_for_owned_algos_clear(account_api, strategy, profiles)
    terminal_statuses = {}
    for profile in profiles:
        status, attempts, transient_errors = await _wait_for_terminal_algo_status(
            account_api,
            strategy,
            profile,
        )
        terminal_statuses[profile] = {
            "status": status,
            "query_attempts": attempts,
            "query_transient_errors": transient_errors,
        }
    finished = [
        profile
        for profile, value in terminal_statuses.items()
        if value["status"] == "FINISHED"
    ]
    evidence["stop_tp_race"] = {
        "both_orders_open_before_trigger": set(initially_visible) == set(profiles),
        "position_after_race": format(race_position, "f"),
        "trigger_timeout": timed_out,
        "pre_cleanup_statuses": pre_cleanup_statuses,
        "terminal_statuses": terminal_statuses,
        "finished_profile_count": len(finished),
        "sibling_cleanup_remaining_profiles": sorted(remaining),
        "no_reverse_samples": no_reverse_samples,
        "all_no_reverse_samples_flat": all(
            Decimal(value) == 0 for value in no_reverse_samples
        ),
        "write_retried": False,
    }
    if set(initially_visible) != set(profiles):
        errors.append("STOP_TP_RACE_NOT_SIMULTANEOUSLY_OPEN")
    if race_position != 0:
        errors.append("STOP_TP_RACE_NOT_FLAT")
    if not timed_out and len(finished) != 1:
        errors.append("STOP_TP_RACE_WINNER_COUNT_MISMATCH")
    if remaining:
        errors.append("STOP_TP_RACE_SIBLING_NOT_CLEARED")
    if not evidence["stop_tp_race"]["all_no_reverse_samples_flat"]:
        errors.append("STOP_TP_RACE_REVERSED_POSITION")


async def _observe_topology(
    node: TradingNode,
    strategy: DemoReduceOnlyTopologyStrategy,
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
    evidence: dict[str, object],
    errors: list[str],
    episode_scope: str,
) -> None:
    account_api: BinanceFuturesAccountHttpAPI | None = None
    try:
        await _wait_for_node_ready(node)
        account_api = _account_api(node, api_key, api_secret, proxy_url)

        hedge_mode = await account_api.query_futures_hedge_mode(recv_window="5000")
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
        if hedge_mode.dualSidePosition:
            errors.append("ACCOUNT_NOT_ONE_WAY")
            return

        preflight = await _responsibility_snapshot(account_api)
        evidence["preflight"] = preflight
        if not _all_clear(preflight):
            errors.append("PREFLIGHT_EXTERNAL_OR_UNKNOWN_RESPONSIBILITY")
            return

        for _ in range(200):
            if strategy.last_bid is not None and strategy.last_ask is not None:
                break
            await asyncio.sleep(0.05)
        if strategy.last_bid is None or strategy.last_ask is None:
            errors.append("QUOTE_NOT_AVAILABLE")
            return

        evidence["armed_only_after_clear_preflight"] = True
        if episode_scope == "PARTIAL_ONLY":
            await _run_partial_tp_episode(
                node,
                account_api,
                strategy,
                evidence,
                errors,
            )
            await asyncio.sleep(0.25)
            postflight = await _responsibility_snapshot(account_api)
            evidence["postflight"] = postflight
            evidence["responsibility_cleared"] = _all_clear(postflight)
            if not evidence["responsibility_cleared"]:
                errors.append("POSTFLIGHT_RESPONSIBILITY_NOT_CLEAR")
            if strategy.errors:
                errors.extend(strategy.errors)
            evidence["strategy"] = {
                "submitted_profiles": list(strategy.submitted),
                "accepted_profiles": sorted(strategy.accepted),
                "filled_profiles": sorted(strategy.filled),
                "canceled_profiles": sorted(strategy.canceled),
                "expired_profiles": sorted(strategy.expired),
                "write_retry": "DISABLED_BY_EXEC_CLIENT_CONFIG",
                "normal_write_path": "ONE_NAUTILUS_STRATEGY",
                "errors": list(strategy.errors),
            }
            return

        strategy.submit_entry_market("ENTRY_A", format(ENTRY_INCREMENT, "f"))
        first_position = await _wait_for_position(account_api, ENTRY_INCREMENT)
        if first_position != ENTRY_INCREMENT:
            errors.append("ENTRY_A_POSITION_NOT_OBSERVED")
            return

        strategy.submit_protective_stop(
            "STOP_A",
            format(ENTRY_INCREMENT, "f"),
            float(strategy.last_bid) * 0.8,
        )
        strategy.submit_entry_market("ENTRY_B", format(ENTRY_INCREMENT, "f"))
        total_position = await _wait_for_position(account_api, TOTAL_POSITION)
        if total_position != TOTAL_POSITION:
            errors.append("ENTRY_B_POSITION_NOT_OBSERVED")
            return

        strategy.submit_protective_stop(
            "STOP_B",
            format(ENTRY_INCREMENT, "f"),
            float(strategy.last_bid) * 0.79,
        )
        # Reverse TP submission order in this episode to prove ordering does not
        # change Binance reduce-only acceptance after protection is established.
        strategy.submit_take_profit(
            "TP2",
            format(ENTRY_INCREMENT, "f"),
            float(strategy.last_ask) * 1.21,
        )
        strategy.submit_take_profit(
            "TP1",
            format(ENTRY_INCREMENT, "f"),
            float(strategy.last_ask) * 1.2,
        )

        visible = await _wait_for_all_algos_open(account_api, strategy)
        topology = _algo_topology_evidence(visible, strategy)
        protection_quantity = (
            sum(
                (Decimal(topology[profile]["quantity"]) for profile in ("STOP_A", "STOP_B")),
                start=Decimal("0"),
            )
            if {"STOP_A", "STOP_B"} <= set(topology)
            else Decimal("0")
        )
        take_profit_quantity = (
            sum(
                (Decimal(topology[profile]["quantity"]) for profile in ("TP1", "TP2")),
                start=Decimal("0"),
            )
            if {"TP1", "TP2"} <= set(topology)
            else Decimal("0")
        )
        evidence["simultaneous_topology"] = {
            "submission_order": list(strategy.submitted),
            "open_profile_count": len(visible),
            "profiles": topology,
            "position_quantity": format(total_position, "f"),
            "protection_quantity": format(protection_quantity, "f"),
            "take_profit_quantity": format(take_profit_quantity, "f"),
            "combined_reduce_only_quantity_exceeds_position_without_rejection": (
                len(visible) == len(ALGO_PROFILES) and not strategy.errors
            ),
            "close_position_used": any(
                bool(profile_evidence["close_position"])
                for profile_evidence in topology.values()
            ),
        }
        if set(visible) != set(ALGO_PROFILES):
            errors.append("SIMULTANEOUS_REDUCE_ONLY_TOPOLOGY_NOT_OPEN")
            return
        if any(value["reduce_only"] is not True for value in topology.values()):
            errors.append("ALGO_REDUCE_ONLY_NOT_TRUE")
        if any(value["quantity_is_explicit"] is not True for value in topology.values()):
            errors.append("ALGO_QUANTITY_NOT_EXPLICIT")
        if any(bool(value["close_position"]) for value in topology.values()):
            errors.append("CLOSE_POSITION_WAS_USED")
        if any(value["working_type"] != "CONTRACT_PRICE" for value in topology.values()):
            errors.append("ALGO_WORKING_TYPE_NOT_CONTRACT_PRICE")
        if any(value["same_uuid32_round_trip"] is not True for value in topology.values()):
            errors.append("ALGO_UUID32_ROUND_TRIP_MISMATCH")

        for profile in ALGO_PROFILES:
            strategy.query_profile(profile)
        await asyncio.sleep(0.5)
        evidence["public_strategy_query_calls"] = list(strategy.public_query_calls)

        strategy.submit_reduce_only_market("EXPLICIT_EXIT", format(TOTAL_POSITION, "f"))
        flat_position = await _wait_for_position(account_api, Decimal("0"))
        evidence["explicit_market_exit"] = {
            "quantity": format(TOTAL_POSITION, "f"),
            "reduce_only": True,
            "submitted_while_all_stop_and_tp_orders_open": True,
            "position_after_exit": format(flat_position, "f"),
        }
        if flat_position != 0:
            errors.append("EXPLICIT_REDUCE_ONLY_MARKET_EXIT_DID_NOT_FLATTEN")
            return

        no_reverse_samples: list[str] = []
        for _ in range(8):
            await asyncio.sleep(0.25)
            no_reverse_samples.append(format(await _position_amount(account_api), "f"))
        evidence["post_exit_no_reverse"] = {
            "samples": no_reverse_samples,
            "all_flat": all(Decimal(value) == 0 for value in no_reverse_samples),
        }
        if not evidence["post_exit_no_reverse"]["all_flat"]:
            errors.append("POSITION_REVERSED_AFTER_COMPETING_REDUCE_ONLY_EXIT")

        for profile in ALGO_PROFILES:
            strategy.cancel_profile(profile)
        remaining = await _wait_for_owned_algos_clear(account_api, strategy)
        evidence["sibling_cleanup"] = {
            "public_cancel_calls": list(strategy.public_cancel_calls),
            "remaining_owned_algo_profiles": sorted(remaining),
        }
        if remaining:
            errors.append("OWNED_ALGO_ORDERS_NOT_CLEARED_BY_PUBLIC_STRATEGY")

        stable_episode_postflight = await _responsibility_snapshot(account_api)
        evidence["stable_episode_postflight"] = stable_episode_postflight
        if _all_clear(stable_episode_postflight):
            await _run_partial_tp_episode(
                node,
                account_api,
                strategy,
                evidence,
                errors,
            )
        else:
            errors.append("STABLE_EPISODE_RESPONSIBILITY_NOT_CLEAR")

        partial_episode_postflight = await _responsibility_snapshot(account_api)
        evidence["partial_episode_postflight"] = partial_episode_postflight
        if _all_clear(partial_episode_postflight):
            await _run_stop_tp_race_episode(
                node,
                account_api,
                strategy,
                evidence,
                errors,
            )
        else:
            errors.append("PARTIAL_EPISODE_RESPONSIBILITY_NOT_CLEAR")

        await asyncio.sleep(0.25)
        postflight = await _responsibility_snapshot(account_api)
        evidence["postflight"] = postflight
        evidence["responsibility_cleared"] = _all_clear(postflight)
        if not evidence["responsibility_cleared"]:
            errors.append("POSTFLIGHT_RESPONSIBILITY_NOT_CLEAR")
        if strategy.errors:
            errors.extend(strategy.errors)
        evidence["strategy"] = {
            "submitted_profiles": list(strategy.submitted),
            "accepted_profiles": sorted(strategy.accepted),
            "filled_profiles": sorted(strategy.filled),
            "canceled_profiles": sorted(strategy.canceled),
            "expired_profiles": sorted(strategy.expired),
            "all_client_order_ids_uuid32": all(
                len(order.client_order_id.value) == 32
                and all(character in "0123456789abcdef" for character in order.client_order_id.value)
                for order in strategy.orders.values()
            ),
            "write_retry": "DISABLED_BY_EXEC_CLIENT_CONFIG",
            "normal_write_path": "ONE_NAUTILUS_STRATEGY",
            "errors": list(strategy.errors),
        }
    finally:
        emergency = {
            "public_responsibility_exit_required": False,
            "fixed_package_cancel_required": False,
            "fixed_package_market_exit_required": False,
        }
        try:
            if account_api is not None:
                position = await _position_amount(account_api)
                if position != 0:
                    emergency["public_responsibility_exit_required"] = True
                    errors.append("PUBLIC_RESPONSIBILITY_EXIT_REQUIRED")
                    side = OrderSide.SELL if position > 0 else OrderSide.BUY
                    strategy.submit_reduce_only_market(
                        "PUBLIC_RESPONSIBILITY_EXIT",
                        format(abs(position), "f"),
                        side,
                    )
                    position = await _wait_for_position(account_api, Decimal("0"))

                strategy.request_public_cleanup()
                await asyncio.sleep(0.5)
                own_ids = {
                    order.client_order_id.value
                    for order in strategy.orders.values()
                }
                ordinary_orders = await account_api.query_open_orders(
                    symbol=SYMBOL,
                    recv_window="5000",
                )
                for venue_order in ordinary_orders:
                    if venue_order.clientOrderId in own_ids:
                        await account_api.cancel_order(
                            symbol=SYMBOL,
                            order_id=venue_order.orderId,
                            orig_client_order_id=None,
                            recv_window="5000",
                        )
                        emergency["fixed_package_cancel_required"] = True
                algo_orders = await account_api.query_open_algo_orders(
                    symbol=SYMBOL,
                    recv_window="5000",
                )
                for venue_order in algo_orders:
                    if venue_order.clientAlgoId in own_ids:
                        await account_api.cancel_algo_order(
                            algo_id=venue_order.algoId,
                            client_algo_id=None,
                            recv_window="5000",
                        )
                        emergency["fixed_package_cancel_required"] = True

                position = await _position_amount(account_api)
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
                    emergency["fixed_package_market_exit_required"] = True

                if (
                    emergency["fixed_package_cancel_required"]
                    or emergency["fixed_package_market_exit_required"]
                ):
                    errors.append("FIXED_PACKAGE_EMERGENCY_WRITE_REQUIRED")
                responsibility = await _responsibility_snapshot(account_api)
                evidence["responsibility_cleared"] = _all_clear(responsibility)
        except Exception as cleanup_exc:
            errors.append(f"EMERGENCY_CLEANUP_FAILED:{type(cleanup_exc).__name__}")
        finally:
            evidence["emergency_cleanup"] = emergency
            await node.stop_async()
            evidence["node_stopped"] = not node.is_running()


def _online_probe(
    evidence_path: Path | None,
    proxy_url: str | None,
    episode_scope: str,
) -> int:
    evidence: dict[str, object] = {
        "operation": (
            "DIRECT_REDUCE_ONLY_PARTIAL_TP"
            if episode_scope == "PARTIAL_ONLY"
            else "DIRECT_REDUCE_ONLY_FULL_TOPOLOGY"
        ),
        "profile": "BINANCE_DEMO",
        "scope": "DIRECT_ISOLATED_QUALIFICATION_ONLY",
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
    strategy: DemoReduceOnlyTopologyStrategy | None = None
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
            strategy = DemoReduceOnlyTopologyStrategy(
                config=StrategyConfig(
                    strategy_id="DIRECTREDUCE",
                    order_id_tag="001",
                    external_order_claims=None,
                    manage_contingent_orders=False,
                    manage_gtd_expiry=False,
                    manage_stop=False,
                ),
            )
            node.trader.add_strategy(strategy)
            observer_task = loop.create_task(
                _observe_topology(
                    node,
                    strategy,
                    api_key,
                    api_secret,
                    proxy_url,
                    evidence,
                    errors,
                    episode_scope,
                ),
            )
            node.run(raise_exception=True)
            if observer_task.done():
                observer_task.result()
            else:
                errors.append("OBSERVER_TASK_NOT_COMPLETED")
                observer_task.cancel()

            evidence["node_stopped"] = not node.is_running()
            if not node.kernel.loop.is_closed():
                node.kernel.cancel_all_tasks()
                evidence["pending_tasks_after_public_cleanup"] = len(
                    [task for task in asyncio.all_tasks(node.kernel.loop) if not task.done()],
                )
            node.dispose()
            evidence["node_disposed"] = True
    except Exception as exc:
        if isinstance(exc, QualificationError):
            errors.append(f"REDUCE_ONLY_TOPOLOGY_PROBE_FAILED:{exc}")
        else:
            errors.append(f"REDUCE_ONLY_TOPOLOGY_PROBE_FAILED:{type(exc).__name__}")
        if node is not None:
            try:
                node.stop()
                evidence["node_stopped"] = not node.is_running()
            except Exception as cleanup_exc:
                errors.append(f"NODE_STOP_FAILED:{type(cleanup_exc).__name__}")
            try:
                if not node.kernel.loop.is_closed():
                    node.kernel.cancel_all_tasks()
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
    if evidence.get("responsibility_cleared") and not errors:
        evidence["status"] = "QUALIFIED"
    elif evidence.get("responsibility_cleared"):
        evidence["status"] = "RESPONSIBILITY_CLEARED_QUALIFICATION_REJECTED"
    else:
        evidence["status"] = "RESPONSIBILITY_NOT_CLEARED"

    rendered = _canonical_json(evidence)
    identities = (
        []
        if strategy is None
        else [order.client_order_id.value for order in strategy.orders.values()]
    )
    if any(identity in rendered for identity in identities):
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_IDENTITY_LEAK_GUARD"]}
    elif api_key is not None and api_key in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    elif api_secret is not None and api_secret in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    _write_evidence(evidence_path, evidence)
    return 0 if evidence.get("status") == "QUALIFIED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qualify simultaneous explicit-quantity reduce-only orders on Binance Demo.",
    )
    parser.add_argument("--evidence-path", type=Path)
    parser.add_argument("--proxy-url")
    parser.add_argument(
        "--episode",
        choices=("full", "partial"),
        default="full",
    )
    args = parser.parse_args()
    episode_scope = "PARTIAL_ONLY" if args.episode == "partial" else "FULL"
    return _online_probe(args.evidence_path, args.proxy_url, episode_scope)


if __name__ == "__main__":
    raise SystemExit(main())
