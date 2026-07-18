from __future__ import annotations

import asyncio
import inspect
import json
from types import SimpleNamespace

from nautilus_trader.adapters.binance.execution import BinanceCommonExecutionClient
from nautilus_trader.adapters.binance.http.error import BinanceClientError
from nautilus_trader.adapters.binance.http.error import BinanceServerError
from nautilus_trader.common.component import Logger
from nautilus_trader.live.retry import RetryManager
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId


class _SilentLog:
    def info(self, _message: str) -> None:
        pass

    def warning(self, _message: str) -> None:
        pass

    def error(self, _message: str) -> None:
        pass

    def debug(self, _message: str) -> None:
        pass


class _FixedClock:
    def timestamp_ns(self) -> int:
        return 1_700_000_000_000_000_000


class _SequencedOrderAccount:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.call_count = 0

    async def query_order(self, **_kwargs: object) -> object | None:
        self.call_count += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _OpenOrderCache:
    def __init__(self, order: object) -> None:
        self._order = order
        self.lookup_count = 0

    def order(self, _client_order_id: ClientOrderId) -> object:
        self.lookup_count += 1
        return self._order


async def _order_status_read_black_box() -> dict[str, object]:
    client_order_id = ClientOrderId("0123456789abcdef0123456789abcdef")
    instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
    command = SimpleNamespace(
        client_order_id=client_order_id,
        venue_order_id=None,
        instrument_id=instrument_id,
    )
    open_order = SimpleNamespace(is_closed=False, strategy_id="B00-STRATEGY")

    async def run_case(responses: list[object], calls: int) -> dict[str, object]:
        account = _SequencedOrderAccount(responses)
        cache = _OpenOrderCache(open_order)
        generated_rejections: list[dict[str, object]] = []
        fake_client = SimpleNamespace(
            _generate_order_status_retries={},
            _max_retries=3,
            _log=_SilentLog(),
            _http_account=account,
            _cache=cache,
            _clock=_FixedClock(),
            generate_order_rejected=lambda **kwargs: generated_rejections.append(kwargs),
        )
        results = []
        for _ in range(calls):
            results.append(
                await BinanceCommonExecutionClient.generate_order_status_report(
                    fake_client,
                    command,
                ),
            )
        return {
            "query_call_count": account.call_count,
            "cache_lookup_count": cache.lookup_count,
            "all_results_none": all(result is None for result in results),
            "technical_rejection_count": len(generated_rejections),
            "retry_counter_cleared": fake_client._generate_order_status_retries == {},
        }

    continuous_error = await run_case(
        [
            BinanceServerError(503, {"code": -1007}, {}),
            BinanceServerError(503, {"code": -1007}, {}),
            BinanceServerError(503, {"code": -1007}, {}),
        ],
        3,
    )
    cache_open_query_missing = await run_case([None], 1)
    explicit_not_found = await run_case(
        [BinanceClientError(400, {"code": -2013, "msg": "Order does not exist."}, {})],
        1,
    )
    return {
        "continuous_transient_error": continuous_error,
        "cache_open_query_missing": cache_open_query_missing,
        "explicit_minus_2013_not_found": explicit_not_found,
    }


async def _zero_write_retry_black_box() -> dict[str, object]:
    calls = 0

    async def fail_once() -> None:
        nonlocal calls
        calls += 1
        raise BinanceServerError(503, {"code": -1007}, {})

    manager = RetryManager[None](
        max_retries=0,
        delay_initial_ms=1,
        delay_max_ms=1,
        backoff_factor=2,
        logger=Logger("B00ZeroWriteRetry"),
        exc_types=(BinanceServerError,),
        retry_check=lambda _exc: True,
    )
    result = await manager.run("write", ["REDACTED_IDENTITY"], fail_once)
    return {
        "call_count": calls,
        "retry_count": manager.retries,
        "result_is_none": result is None,
        "manager_result": manager.result,
        "last_exception_type": type(manager.last_exception).__name__,
    }


def main() -> int:
    init_source = inspect.getsource(BinanceCommonExecutionClient.__init__)
    submit_source = inspect.getsource(BinanceCommonExecutionClient._submit_order_inner)
    query_source = inspect.getsource(
        BinanceCommonExecutionClient.generate_order_status_report,
    )
    cancel_source = inspect.getsource(BinanceCommonExecutionClient._cancel_order_single)
    black_box = asyncio.run(_zero_write_retry_black_box())
    read_black_box = asyncio.run(_order_status_read_black_box())
    source_contract = {
        "write_pool_none_maps_to_zero": "max_retries=config.max_retries or 0" in init_source,
        "read_status_none_maps_to_three": "self._max_retries = config.max_retries or 3"
        in init_source,
        "submit_invokes_one_retry_manager_operation": (
            submit_source.count("retry_manager.run(") == 1
        ),
        "ordinary_not_found_returns_no_report": (
            "if _is_no_such_order(e):" in query_source and "return None" in query_source
        ),
        "continuous_read_error_can_generate_technical_rejected": (
            "if retries >= self._max_retries:" in query_source
            and "self.generate_order_rejected(" in query_source
        ),
        "cancel_requires_cache_order": (
            "order: Order | None = self._cache.order(client_order_id)" in cancel_source
            and "if order is None:" in cancel_source
        ),
        "closed_order_cancel_does_not_reach_exchange": (
            "if order.is_closed:" in cancel_source
            and "will not send to exchange" in cancel_source
        ),
    }
    errors: list[str] = []
    if black_box != {
        "call_count": 1,
        "retry_count": 0,
        "result_is_none": True,
        "manager_result": False,
        "last_exception_type": "BinanceServerError",
    }:
        errors.append("ZERO_WRITE_RETRY_BLACK_BOX_MISMATCH")
    if read_black_box != {
        "continuous_transient_error": {
            "query_call_count": 3,
            "cache_lookup_count": 3,
            "all_results_none": True,
            "technical_rejection_count": 1,
            "retry_counter_cleared": True,
        },
        "cache_open_query_missing": {
            "query_call_count": 1,
            "cache_lookup_count": 0,
            "all_results_none": True,
            "technical_rejection_count": 0,
            "retry_counter_cleared": True,
        },
        "explicit_minus_2013_not_found": {
            "query_call_count": 1,
            "cache_lookup_count": 0,
            "all_results_none": True,
            "technical_rejection_count": 0,
            "retry_counter_cleared": True,
        },
    }:
        errors.append("ORDER_STATUS_READ_BLACK_BOX_MISMATCH")
    errors.extend(name for name, matched in source_contract.items() if not matched)
    evidence = {
        "stage": "B00_ORDER_FAILURE_SEMANTICS",
        "zero_write_retry_black_box": black_box,
        "order_status_read_black_box": read_black_box,
        "fixed_source_contract": source_contract,
        "required_halpha_interpretation": {
            "write_timeout_or_crash": "SUBMITTED_UNKNOWN",
            "automatic_resubmit_same_identity": False,
            "next_action": "QUERY_ORIGINAL_UUID32_ONLY",
            "single_not_found_proves_not_submitted": False,
            "technical_synthetic_rejected_is_product_terminal": False,
            "cancel_unknown_identity": False,
            "cancel_only_after_open_is_proven": True,
        },
        "errors": errors,
        "status": "QUALIFIED_COMPONENT_SEMANTICS" if not errors else "REJECTED",
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
