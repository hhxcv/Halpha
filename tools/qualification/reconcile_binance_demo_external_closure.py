"""Reconcile one explicitly selected Binance Demo emergency close into a Review.

This tool performs signed GET queries only.  The selected order is persisted as
unclaimed account facts and is never rewritten as a Halpha execution action.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import keyring
import psycopg


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import get_cached_binance_http_client
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.common.enums import BinanceKeyType
from nautilus_trader.adapters.binance.futures.http.account import (
    BinanceFuturesAccountHttpAPI,
)
from nautilus_trader.common.component import LiveClock

from halpha.configuration import executor_settings, load_settings
from halpha.executor.runtime import _connect_product_database
from halpha.outcomes.account_reconciliation import (
    AccountReconciliationError,
    build_external_account_closure_facts,
)
from halpha.outcomes.service import OutcomeApplicationService
from halpha.outcomes.trade_result import summarize_trade_result
from halpha.venue_integration.repository import PostgreSQLVenueFactRepository
from halpha.winvault import executor_secret_resolver


def _enum_value(value: object) -> str:
    token = getattr(value, "value", value)
    return str(token)


async def _read_order_and_trades(
    *,
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
    symbol: str,
    order_id: int,
    start_time_ms: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], frozenset[str]]:
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
    account = BinanceFuturesAccountHttpAPI(
        client,
        clock,
        BinanceAccountType.USDT_FUTURES,
    )
    order = await account.query_order(
        symbol=symbol,
        order_id=order_id,
        recv_window="5000",
    )
    selected = await account.query_user_trades(
        symbol=symbol,
        order_id=order_id,
        limit=1000,
        recv_window="5000",
    )
    if not selected:
        raise AccountReconciliationError("EXTERNAL_ORDER_TRADES_MISSING")
    end_time_ms = max(int(item.time or 0) for item in selected) + 1
    episode = await account.query_user_trades(
        symbol=symbol,
        start_time=start_time_ms,
        end_time=end_time_ms,
        limit=1000,
        recv_window="5000",
    )
    order_data = {
        "order_id": str(order.orderId),
        "client_order_id": order.clientOrderId,
        "symbol": order.symbol,
        "status": _enum_value(order.status),
        "side": _enum_value(order.side),
        "order_type": _enum_value(order.type),
        "executed_quantity": order.executedQty,
        "average_price": order.avgPrice,
        "reduce_only": order.reduceOnly,
        "update_time_ms": order.updateTime or order.time,
    }
    trades = [
        {
            "trade_id": str(item.id if item.id is not None else item.tradeId),
            "order_id": str(item.orderId),
            "symbol": item.symbol,
            "side": (
                _enum_value(item.side)
                if item.side is not None
                else ("BUY" if item.buyer else "SELL")
            ),
            "price": item.price,
            "quantity": item.qty,
            "commission": item.commission,
            "commission_asset": item.commissionAsset,
            "realized_pnl": item.realizedPnl,
            "time_ms": item.time,
            "maker": item.maker if item.maker is not None else item.isMaker,
        }
        for item in selected
    ]
    episode_ids = frozenset(
        str(item.id if item.id is not None else item.tradeId) for item in episode
    )
    return order_data, trades, episode_ids


def reconcile(
    *,
    config_path: Path,
    activation_id: str,
    external_order_id: int,
) -> dict[str, Any]:
    settings = load_settings(config_path)
    if settings.release.profile != "BINANCE_DEMO":
        raise AccountReconciliationError("DEMO_PROFILE_REQUIRED")
    role = executor_settings(settings)
    resolver = executor_secret_resolver(keyring.get_keyring(), role)
    database_password = resolver.resolve(
        role.executor.database_credential_reference
    ).get_secret_value()
    key_ref = role.executor.binance_api_key_reference
    secret_ref = role.executor.binance_api_secret_reference
    if key_ref is None or secret_ref is None:
        raise AccountReconciliationError("BINANCE_CREDENTIAL_REFERENCE_REQUIRED")
    api_key = resolver.resolve(key_ref).get_secret_value()
    api_secret = resolver.resolve(secret_ref).get_secret_value()
    proxy_ref = role.executor.runtime_proxy_reference
    proxy_url = (
        resolver.resolve(proxy_ref).get_secret_value()
        if proxy_ref is not None
        else None
    )
    connection = _connect_product_database(
        psycopg.connect,
        database_name=settings.release.database_name,
        password=database_password,
    )
    try:
        with connection.transaction():
            activation = connection.execute(
                """
                SELECT account_ref, instrument_ref, direction, lifecycle
                FROM halpha.plan_activation
                WHERE environment_id = %s AND activation_id = %s
                FOR UPDATE
                """,
                (settings.release.environment_id, activation_id),
            ).fetchone()
            if activation is None:
                raise AccountReconciliationError("ACTIVATION_NOT_FOUND")
            if str(activation[3]) != "COMPLETED":
                raise AccountReconciliationError("ACTIVATION_NOT_COMPLETE")
            action_rows = connection.execute(
                """
                SELECT execution_action_id, action_kind
                FROM halpha.execution_action
                WHERE environment_id = %s AND activation_id = %s
                """,
                (settings.release.environment_id, activation_id),
            ).fetchall()
            fact_rows = connection.execute(
                """
                SELECT kind, payload, action_ref, source_time
                FROM halpha.venue_fact
                WHERE environment_id = %s AND activation_ref = %s
                ORDER BY cutoff, venue_fact_id
                """,
                (settings.release.environment_id, activation_id),
            ).fetchall()
            attributed_facts = [
                {
                    "kind": str(row[0]),
                    "payload": dict(row[1]),
                    "action_ref": str(row[2]) if row[2] is not None else None,
                    "source_time": row[3],
                }
                for row in fact_rows
            ]
            attributed_result = summarize_trade_result(
                direction=str(activation[2]),
                action_kinds={str(row[0]): str(row[1]) for row in action_rows},
                facts=attributed_facts,
            )
            if attributed_result["closed"] is True:
                raise AccountReconciliationError("ACTIVATION_RESULT_ALREADY_CLOSED")
            open_quantity = attributed_result.get("position_quantity")
            entry_price = attributed_result.get("average_entry_price")
            if open_quantity in {None, "0"} or entry_price is None:
                raise AccountReconciliationError("ATTRIBUTED_ENTRY_FACTS_INCOMPLETE")
            entry_times = [
                row[3]
                for row in fact_rows
                if str(row[0]) == "FILL" and row[3] is not None
            ]
            if not entry_times:
                raise AccountReconciliationError("ATTRIBUTED_ENTRY_TIME_MISSING")
            attributed_trade_ids = frozenset(
                str(dict(row[1]).get("trade_id"))
                for row in fact_rows
                if str(row[0]) == "FILL" and dict(row[1]).get("trade_id") is not None
            )
            instrument_ref = str(activation[1])
            if not instrument_ref.endswith("-PERP"):
                raise AccountReconciliationError("RECONCILIATION_INSTRUMENT_UNSUPPORTED")
            symbol = instrument_ref[:-5]
            order, external_trades, episode_trade_ids = asyncio.run(
                _read_order_and_trades(
                    api_key=api_key,
                    api_secret=api_secret,
                    proxy_url=proxy_url,
                    symbol=symbol,
                    order_id=external_order_id,
                    start_time_ms=int(min(entry_times).timestamp() * 1000),
                )
            )
            selected_trade_ids = frozenset(
                str(item["trade_id"]) for item in external_trades
            )
            expected_episode_ids = attributed_trade_ids | selected_trade_ids
            if episode_trade_ids != expected_episode_ids:
                raise AccountReconciliationError(
                    "ACCOUNT_EPISODE_CONTAINS_OTHER_TRADES"
                )
            observed_at = datetime.now(UTC)
            facts = build_external_account_closure_facts(
                environment_id=settings.release.environment_id,
                account_ref=str(activation[0]),
                instrument_ref=instrument_ref,
                activation_id=activation_id,
                direction=str(activation[2]),
                open_quantity=str(abs(Decimal(str(open_quantity)))),
                average_entry_price=str(entry_price),
                attributed_trade_ids=attributed_trade_ids,
                order=order,
                trades=external_trades,
                observed_at=observed_at,
            )
            repository = PostgreSQLVenueFactRepository(
                connection,
                settings.release.environment_id,
            )
            persisted_fact_ids: list[str] = []
            for fact in facts:
                existing = repository.find_by_source(fact)
                if existing is not None:
                    if (
                        existing.payload != fact.payload
                        or existing.impact_scope != fact.impact_scope
                    ):
                        raise AccountReconciliationError(
                            "EXTERNAL_FACT_SOURCE_CONFLICT"
                        )
                    persisted_fact_ids.append(existing.venue_fact_id)
                    continue
                repository.insert(fact)
                persisted_fact_ids.append(fact.venue_fact_id)
            review = OutcomeApplicationService(
                connection,
                settings.release.environment_id,
            ).update_activation_review(
                activation_id,
                fact_cutoff=observed_at,
                observed_at=observed_at,
            )
            result = dict(review.account_result.get("trade_result", {}))
            if not (
                result.get("closed") is True
                and result.get("calculation_complete") is True
                and result.get("result_scope")
                == "ACCOUNT_FACTS_WITH_EXTERNAL_CLOSURE"
            ):
                raise AccountReconciliationError(
                    "RECONCILED_ACCOUNT_RESULT_INCOMPLETE"
                )
            return {
                "status": "RECONCILED",
                "read_only_exchange_query": True,
                "exchange_write_called": False,
                "activation_id": activation_id,
                "external_order_id": str(external_order_id),
                "external_trade_ids": sorted(selected_trade_ids),
                "venue_fact_ids": persisted_fact_ids,
                "review_id": review.review_id,
                "review_version": review.review_version,
                "result_scope": result["result_scope"],
                "gross_pnl": result["gross_pnl"],
                "commission": result["commission"],
                "net_pnl": result["net_pnl"],
            }
    finally:
        connection.close()
        get_cached_binance_http_client.cache_clear()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bind one explicitly selected reduce-only Binance Demo order to the "
            "account result of a completed activation."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--activation-id", required=True)
    parser.add_argument("--external-order-id", type=int, required=True)
    args = parser.parse_args()
    try:
        result = reconcile(
            config_path=args.config.resolve(),
            activation_id=args.activation_id,
            external_order_id=args.external_order_id,
        )
    except Exception as exc:
        result = {
            "status": "REJECTED",
            "reason": str(exc),
            "exception_type": type(exc).__name__,
            "read_only_exchange_query": True,
            "exchange_write_called": False,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "RECONCILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
