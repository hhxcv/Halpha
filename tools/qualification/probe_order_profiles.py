from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from nautilus_trader.adapters.binance.execution import BinanceCommonExecutionClient
from nautilus_trader.adapters.binance.futures.enums import BinanceFuturesEnumParser
from nautilus_trader.common.component import TestClock
from nautilus_trader.common.factories import OrderFactory
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.enums import TriggerType
from nautilus_trader.model.enums import order_type_to_str
from nautilus_trader.model.enums import time_in_force_to_str
from nautilus_trader.model.enums import trigger_type_to_str
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


UUID32_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _new_client_order_id() -> ClientOrderId:
    return ClientOrderId(uuid4().hex)


def _profile(
    profile_id: str,
    order,
    *,
    expected_type: OrderType,
    expected_reduce_only: bool,
) -> dict[str, object]:
    client_order_id = order.client_order_id.value
    return {
        "id": profile_id,
        "order_type": order_type_to_str(order.order_type),
        "order_type_matches": order.order_type == expected_type,
        "quantity_is_explicit": order.quantity is not None,
        "reduce_only": order.is_reduce_only,
        "reduce_only_matches": order.is_reduce_only == expected_reduce_only,
        "time_in_force": time_in_force_to_str(order.time_in_force),
        "client_order_id_uuid32": UUID32_PATTERN.fullmatch(client_order_id) is not None,
        "client_order_id_has_hyphens": "-" in client_order_id,
        "client_order_id_length": len(client_order_id),
    }


def main() -> int:
    errors: list[str] = []
    factory = OrderFactory(
        trader_id=TraderId("DIRECT-QUAL-001"),
        strategy_id=StrategyId("DIRECTPROBE-001"),
        clock=TestClock(),
    )
    instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
    quantity = Quantity.from_str("0.001")

    entry_market = factory.market(
        instrument_id=instrument_id,
        order_side=OrderSide.BUY,
        quantity=quantity,
        client_order_id=_new_client_order_id(),
    )
    entry_limit = factory.limit(
        instrument_id=instrument_id,
        order_side=OrderSide.BUY,
        quantity=quantity,
        price=Price.from_str("50000.0"),
        time_in_force=TimeInForce.GTC,
        client_order_id=_new_client_order_id(),
    )
    entry_stop_market = factory.stop_market(
        instrument_id=instrument_id,
        order_side=OrderSide.BUY,
        quantity=quantity,
        trigger_price=Price.from_str("60000.0"),
        trigger_type=TriggerType.LAST_PRICE,
        reduce_only=False,
        client_order_id=_new_client_order_id(),
    )
    protective_stop = factory.stop_market(
        instrument_id=instrument_id,
        order_side=OrderSide.SELL,
        quantity=quantity,
        trigger_price=Price.from_str("40000.0"),
        trigger_type=TriggerType.LAST_PRICE,
        reduce_only=True,
        client_order_id=_new_client_order_id(),
    )
    take_profit_1 = factory.market_if_touched(
        instrument_id=instrument_id,
        order_side=OrderSide.SELL,
        quantity=Quantity.from_str("0.0005"),
        trigger_price=Price.from_str("65000.0"),
        trigger_type=TriggerType.LAST_PRICE,
        reduce_only=True,
        client_order_id=_new_client_order_id(),
    )
    take_profit_2 = factory.market_if_touched(
        instrument_id=instrument_id,
        order_side=OrderSide.SELL,
        quantity=Quantity.from_str("0.0005"),
        trigger_price=Price.from_str("70000.0"),
        trigger_type=TriggerType.LAST_PRICE,
        reduce_only=True,
        client_order_id=_new_client_order_id(),
    )
    reduce_or_close_market = factory.market(
        instrument_id=instrument_id,
        order_side=OrderSide.SELL,
        quantity=quantity,
        reduce_only=True,
        client_order_id=_new_client_order_id(),
    )

    profiles = [
        _profile(
            "ENTRY_MARKET",
            entry_market,
            expected_type=OrderType.MARKET,
            expected_reduce_only=False,
        ),
        _profile(
            "ENTRY_LIMIT",
            entry_limit,
            expected_type=OrderType.LIMIT,
            expected_reduce_only=False,
        ),
        _profile(
            "ENTRY_STOP_MARKET",
            entry_stop_market,
            expected_type=OrderType.STOP_MARKET,
            expected_reduce_only=False,
        ),
        {
            "id": "CANCEL_ORDER",
            "reuses_target_client_order_id": True,
            "target_profile": "ENTRY_LIMIT",
            "unknown_policy": "QUERY_ORIGINAL_IDENTITY_ONLY",
            "client_order_id_uuid32": UUID32_PATTERN.fullmatch(
                entry_limit.client_order_id.value,
            )
            is not None,
        },
        _profile(
            "PROTECTIVE_STOP_REDUCE_ONLY",
            protective_stop,
            expected_type=OrderType.STOP_MARKET,
            expected_reduce_only=True,
        ),
        _profile(
            "TAKE_PROFIT_1",
            take_profit_1,
            expected_type=OrderType.MARKET_IF_TOUCHED,
            expected_reduce_only=True,
        ),
        _profile(
            "TAKE_PROFIT_2",
            take_profit_2,
            expected_type=OrderType.MARKET_IF_TOUCHED,
            expected_reduce_only=True,
        ),
        _profile(
            "REDUCE_OR_CLOSE_MARKET",
            reduce_or_close_market,
            expected_type=OrderType.MARKET,
            expected_reduce_only=True,
        ),
    ]

    enum_parser = BinanceFuturesEnumParser()
    adapter_mapping = {
        "ENTRY_MARKET": enum_parser.parse_internal_order_type(entry_market).value,
        "ENTRY_LIMIT": enum_parser.parse_internal_order_type(entry_limit).value,
        "ENTRY_STOP_MARKET": enum_parser.parse_internal_order_type(entry_stop_market).value,
        "PROTECTIVE_STOP_REDUCE_ONLY": enum_parser.parse_internal_order_type(
            protective_stop,
        ).value,
        "TAKE_PROFIT_1": enum_parser.parse_internal_order_type(take_profit_1).value,
        "TAKE_PROFIT_2": enum_parser.parse_internal_order_type(take_profit_2).value,
        "REDUCE_OR_CLOSE_MARKET": enum_parser.parse_internal_order_type(
            reduce_or_close_market,
        ).value,
    }

    market_source = inspect.getsource(BinanceCommonExecutionClient._submit_market_order)
    stop_market_source = inspect.getsource(
        BinanceCommonExecutionClient._submit_stop_market_order,
    )
    submit_source = inspect.getsource(BinanceCommonExecutionClient._submit_order_inner)
    init_source = inspect.getsource(BinanceCommonExecutionClient.__init__)
    fixed_adapter_contract = {
        "market_wire_omits_time_in_force": "time_in_force=" not in market_source,
        "stop_last_price_maps_contract_price": (
            'working_type = "CONTRACT_PRICE"' in stop_market_source
        ),
        "conditionals_use_algo_order_api": "new_algo_order" in stop_market_source,
        "explicit_quantity_path_present": (
            "quantity=str(order.quantity)" in stop_market_source
        ),
        "reduce_only_path_present": (
            "reduce_only=self._determine_reduce_only_str(order)" in stop_market_source
        ),
        "close_position_is_opt_in_parameter": (
            "if close_position:" in stop_market_source
            and "close_position = self._extract_close_position(order, params)" in submit_source
        ),
        "zero_write_retry_when_max_retries_none": "max_retries=config.max_retries or 0"
        in init_source,
    }

    conditional_profiles = (entry_stop_market, protective_stop, take_profit_1, take_profit_2)
    trigger_contract = {
        order.client_order_id.value: trigger_type_to_str(order.trigger_type)
        for order in conditional_profiles
    }
    trigger_values_are_last_price = all(
        value == "LAST_PRICE" for value in trigger_contract.values()
    )

    for profile in profiles:
        if not profile.get("client_order_id_uuid32", False):
            errors.append(f"PROFILE_IDENTITY_INVALID:{profile['id']}")
        if profile.get("client_order_id_has_hyphens", False):
            errors.append(f"PROFILE_IDENTITY_HAS_HYPHENS:{profile['id']}")
        if profile.get("order_type_matches") is False:
            errors.append(f"PROFILE_ORDER_TYPE_MISMATCH:{profile['id']}")
        if profile.get("reduce_only_matches") is False:
            errors.append(f"PROFILE_REDUCE_ONLY_MISMATCH:{profile['id']}")
        if profile.get("quantity_is_explicit") is False:
            errors.append(f"PROFILE_QUANTITY_NOT_EXPLICIT:{profile['id']}")
    if len({order.client_order_id.value for order in (
        entry_market,
        entry_limit,
        entry_stop_market,
        protective_stop,
        take_profit_1,
        take_profit_2,
        reduce_or_close_market,
    )}) != 7:
        errors.append("CLIENT_ORDER_IDS_NOT_UNIQUE")
    if not trigger_values_are_last_price:
        errors.append("CONDITIONAL_TRIGGER_NOT_LAST_PRICE")
    if not all(fixed_adapter_contract.values()):
        errors.append("FIXED_ADAPTER_CONTRACT_MISMATCH")
    if adapter_mapping != {
        "ENTRY_MARKET": "MARKET",
        "ENTRY_LIMIT": "LIMIT",
        "ENTRY_STOP_MARKET": "STOP_MARKET",
        "PROTECTIVE_STOP_REDUCE_ONLY": "STOP_MARKET",
        "TAKE_PROFIT_1": "TAKE_PROFIT_MARKET",
        "TAKE_PROFIT_2": "TAKE_PROFIT_MARKET",
        "REDUCE_OR_CLOSE_MARKET": "MARKET",
    }:
        errors.append("BINANCE_ORDER_TYPE_MAPPING_MISMATCH")

    evidence = {
        "operation": "DIRECT_ORDER_PROFILE_CAPABILITY",
        "profiles": profiles,
        "profile_count": len(profiles),
        "identity": {
            "format": "UUID32_LOWERCASE_HEX_NO_HYPHENS",
            "owner": "PENDING_ACTION_CALLER",
            "generated_once_then_explicitly_passed": True,
            "submit_query_cancel_restart_reuse_required": True,
            "actual_values_persisted_in_evidence": False,
        },
        "conditional_trigger": {
            "internal": "LAST_PRICE",
            "binance_working_type": "CONTRACT_PRICE",
            "all_profiles_match": trigger_values_are_last_price,
        },
        "adapter_mapping": adapter_mapping,
        "fixed_adapter_contract": fixed_adapter_contract,
        "forbidden_profile_use": {
            "modify_in_place": False,
            "bracket_or_oco": False,
            "trailing_stop": False,
            "framework_market_exit": False,
            "close_position": False,
            "automatic_split_or_fallback": False,
        },
        "automatic_write_retry": "DISABLED",
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
