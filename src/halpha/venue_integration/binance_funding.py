"""Read Binance USDT futures funding income through Nautilus' shared client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
from typing import Protocol

from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from halpha.domain_values import canonical_decimal


FUNDING_INCOME_PATH = "/fapi/v1/income"
FUNDING_INCOME_TYPE = "FUNDING_FEE"
FUNDING_PAGE_LIMIT = 100
FUNDING_MAX_PAGES = 100


class BinanceClock(Protocol):
    def timestamp_ms(self) -> int: ...


class BinanceSignedHttpClient(Protocol):
    async def sign_request(self, **kwargs: object) -> bytes: ...


class BinanceFundingContractError(RuntimeError):
    """The pinned Nautilus client returned an unusable funding response."""


@dataclass(frozen=True, slots=True)
class FundingIncomeRecord:
    transaction_id: str
    symbol: str
    income: str
    asset: str
    source_time: datetime


def _parse_page(
    raw: bytes,
    *,
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
) -> tuple[FundingIncomeRecord, ...]:
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        raise BinanceFundingContractError(
            "FUNDING_INCOME_RESPONSE_NOT_JSON"
        ) from None
    if not isinstance(decoded, list):
        raise BinanceFundingContractError("FUNDING_INCOME_RESPONSE_NOT_LIST")
    records: list[FundingIncomeRecord] = []
    for item in decoded:
        if not isinstance(item, dict):
            raise BinanceFundingContractError(
                "FUNDING_INCOME_RESPONSE_SCHEMA_MISMATCH"
            )
        if (
            item.get("symbol") != symbol
            or item.get("incomeType") != FUNDING_INCOME_TYPE
            or item.get("asset") != "USDT"
            or type(item.get("time")) is not int
            or type(item.get("tranId")) is not int
        ):
            raise BinanceFundingContractError(
                "FUNDING_INCOME_RESPONSE_SCHEMA_MISMATCH"
            )
        event_time_ms = int(item["time"])
        if not start_time_ms <= event_time_ms <= end_time_ms:
            raise BinanceFundingContractError(
                "FUNDING_INCOME_TIME_OUTSIDE_QUERY"
            )
        try:
            income = Decimal(str(item["income"]))
        except (InvalidOperation, KeyError, TypeError, ValueError):
            raise BinanceFundingContractError(
                "FUNDING_INCOME_AMOUNT_INVALID"
            ) from None
        if not income.is_finite():
            raise BinanceFundingContractError("FUNDING_INCOME_AMOUNT_INVALID")
        records.append(
            FundingIncomeRecord(
                transaction_id=str(item["tranId"]),
                symbol=symbol,
                income=canonical_decimal(income),
                asset="USDT",
                source_time=datetime.fromtimestamp(
                    event_time_ms / 1000,
                    tz=UTC,
                ),
            )
        )
    return tuple(records)


async def query_funding_income(
    client: BinanceSignedHttpClient,
    clock: BinanceClock,
    *,
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    recv_window: str = "5000",
) -> tuple[FundingIncomeRecord, ...]:
    """Return a deduplicated funding window using Binance's signed read API."""

    if (
        start_time.utcoffset() is None
        or end_time.utcoffset() is None
        or end_time < start_time
    ):
        raise BinanceFundingContractError("FUNDING_INCOME_TIME_RANGE_INVALID")
    start_time_ms = int(start_time.timestamp() * 1000)
    end_time_ms = int(end_time.timestamp() * 1000)
    records: dict[str, FundingIncomeRecord] = {}
    previous_ids: tuple[str, ...] | None = None
    for page in range(1, FUNDING_MAX_PAGES + 1):
        raw = await client.sign_request(
            http_method=HttpMethod.GET,
            url_path=FUNDING_INCOME_PATH,
            payload={
                "symbol": symbol,
                "incomeType": FUNDING_INCOME_TYPE,
                "startTime": str(start_time_ms),
                "endTime": str(end_time_ms),
                "page": str(page),
                "limit": str(FUNDING_PAGE_LIMIT),
                "timestamp": str(clock.timestamp_ms()),
                "recvWindow": recv_window,
            },
            ratelimiter_keys=[
                f"binance:{FUNDING_INCOME_PATH}",
                "binance:global",
            ],
        )
        current = _parse_page(
            raw,
            symbol=symbol,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
        current_ids = tuple(record.transaction_id for record in current)
        if current and current_ids == previous_ids:
            raise BinanceFundingContractError(
                "FUNDING_INCOME_PAGINATION_NOT_ADVANCING"
            )
        for record in current:
            existing = records.get(record.transaction_id)
            if existing is not None and existing != record:
                raise BinanceFundingContractError(
                    "FUNDING_INCOME_IDENTITY_CONFLICT"
                )
            records[record.transaction_id] = record
        previous_ids = current_ids
        if len(current) < FUNDING_PAGE_LIMIT and (current or page > 1):
            return tuple(
                sorted(
                    records.values(),
                    key=lambda item: (
                        item.source_time,
                        item.transaction_id,
                    ),
                )
            )
    raise BinanceFundingContractError(
        "FUNDING_INCOME_PAGINATION_LIMIT_EXCEEDED"
    )
