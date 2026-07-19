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

from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import get_cached_binance_http_client
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.common.enums import BinanceKeyType
from nautilus_trader.adapters.binance.futures.http.account import (
    BinanceFuturesAccountHttpAPI,
)
from nautilus_trader.adapters.binance.http.error import BinanceError
from nautilus_trader.common.component import LiveClock

from tools.qualification.probe_binance_demo_clients import QualificationError
from tools.qualification.probe_binance_demo_clients import _acquire_executor_mutex
from tools.qualification.probe_binance_demo_clients import _canonical_json
from tools.qualification.probe_binance_demo_clients import _load_credentials
from tools.qualification.probe_binance_demo_clients import _release_executor_mutex
from tools.qualification.probe_binance_demo_clients import _validate_proxy_url
from tools.qualification.probe_binance_demo_clients import _without_binance_credential_environment
from tools.qualification.probe_binance_demo_clients import _write_evidence


UUID32_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _error_code(exc: BinanceError) -> int | None:
    message = exc.message
    if isinstance(message, dict) and isinstance(message.get("code"), int):
        return message["code"]
    if isinstance(message, str):
        try:
            decoded = json.loads(message)
        except ValueError:
            return None
        if isinstance(decoded, dict) and isinstance(decoded.get("code"), int):
            return decoded["code"]
    return None


async def _query_matrix(
    client_order_id: str,
    algo_id: int,
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
    variants = {
        "ALGO_ID_ONLY": {"algo_id": algo_id, "client_algo_id": None},
        "CLIENT_ALGO_ID_ONLY": {"algo_id": None, "client_algo_id": client_order_id},
        "BOTH_IDENTITIES": {"algo_id": algo_id, "client_algo_id": client_order_id},
    }
    results: dict[str, object] = {}
    for name, parameters in variants.items():
        try:
            order = await account_api.query_algo_order(
                algo_id=parameters["algo_id"],
                client_algo_id=parameters["client_algo_id"],
                recv_window="5000",
            )
            results[name] = {
                "result": "FOUND",
                "algo_id_exact_round_trip": order.algoId == algo_id,
                "client_algo_id_exact_round_trip": order.clientAlgoId == client_order_id,
                "status": order.algoStatus,
                "order_type": order.orderType,
                "quantity_is_explicit": order.quantity is not None,
                "actual_identities_persisted": False,
            }
        except BinanceError as exc:
            results[name] = {
                "result": "BINANCE_ERROR",
                "http_status": exc.status,
                "binance_error_code": _error_code(exc),
                "raw_message_persisted": False,
            }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Binance Demo algo-order identity query matrix.",
    )
    parser.add_argument("--client-order-id", required=True)
    parser.add_argument("--algo-id", required=True, type=int)
    parser.add_argument("--proxy-url")
    parser.add_argument("--evidence-path", type=Path)
    args = parser.parse_args()
    if UUID32_PATTERN.fullmatch(args.client_order_id) is None:
        raise SystemExit("client-order-id must be UUID32 lowercase hexadecimal")
    if args.algo_id <= 0:
        raise SystemExit("algo-id must be positive")

    evidence: dict[str, object] = {
        "operation": "DIRECT_ALGO_QUERY_IDENTITY_MATRIX",
        "profile": "BINANCE_DEMO",
        "read_only": True,
        "actual_identities_persisted": False,
        "proxy": "RUNTIME_LOOPBACK_ARGUMENT" if args.proxy_url is not None else "DISABLED",
    }
    errors: list[str] = []
    mutex = None
    api_key: str | None = None
    api_secret: str | None = None
    try:
        proxy_url = _validate_proxy_url(args.proxy_url)
        mutex = _acquire_executor_mutex()
        api_key, api_secret, backend_name = _load_credentials()
        evidence["credential_backend"] = backend_name
        with _without_binance_credential_environment() as environment_was_populated:
            evidence["credential_environment_sanitized"] = True
            evidence["credential_environment_had_values"] = environment_was_populated
            evidence["matrix"] = asyncio.run(
                _query_matrix(
                    args.client_order_id,
                    args.algo_id,
                    api_key,
                    api_secret,
                    proxy_url,
                ),
            )
    except Exception as exc:
        if isinstance(exc, QualificationError):
            errors.append(f"ALGO_QUERY_MATRIX_FAILED:{exc}")
        else:
            errors.append(f"ALGO_QUERY_MATRIX_FAILED:{type(exc).__name__}")
    finally:
        get_cached_binance_http_client.cache_clear()
        if mutex is not None:
            try:
                _release_executor_mutex(mutex)
            except Exception as exc:
                errors.append(f"EXECUTOR_MUTEX_RELEASE_FAILED:{type(exc).__name__}")
    evidence["errors"] = sorted(set(errors))
    evidence["status"] = "QUALIFIED_READ_MATRIX" if not errors else "REJECTED"
    rendered = _canonical_json(evidence)
    if args.client_order_id in rendered or str(args.algo_id) in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_IDENTITY_LEAK_GUARD"]}
    elif api_key is not None and api_key in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    elif api_secret is not None and api_secret in rendered:
        evidence = {"status": "REJECTED", "errors": ["EVIDENCE_SECRET_LEAK_GUARD"]}
    _write_evidence(args.evidence_path, evidence)
    return 0 if evidence.get("status") == "QUALIFIED_READ_MATRIX" else 1


if __name__ == "__main__":
    raise SystemExit(main())
