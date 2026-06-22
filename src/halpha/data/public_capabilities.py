from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class PublicDataClassCapability:
    data_class: str
    collection_status: str
    view_status: str
    request_classes: tuple[str, ...] = ()
    availability_period: str | None = None
    unavailable_reason: str | None = None
    limitations: tuple[str, ...] = ()
    downstream_implication: str | None = None


SUPPORTED_DERIVATIVES_MARKET_SOURCES: Final[set[str]] = {"binance_usdm"}
SUPPORTED_DERIVATIVES_PERIODS: Final[set[str]] = {
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
}

DERIVATIVES_LIQUIDATION_SUMMARY_PERIOD: Final[str] = "source_availability"
DERIVATIVES_LIQUIDATION_UNAVAILABLE_REASON: Final[str] = (
    "binance_usdm public liquidation data is available as real-time WebSocket force-order streams; "
    "periodic unauthenticated REST liquidation summaries are not available for the current product path."
)

DERIVATIVES_DATA_CLASS_CAPABILITIES: Final[dict[str, PublicDataClassCapability]] = {
    "basis": PublicDataClassCapability(
        data_class="basis",
        collection_status="implemented",
        view_status="implemented",
        request_classes=("basis",),
    ),
    "funding_rate": PublicDataClassCapability(
        data_class="funding_rate",
        collection_status="implemented",
        view_status="implemented",
        request_classes=("funding_rate_history",),
    ),
    "liquidation_summary": PublicDataClassCapability(
        data_class="liquidation_summary",
        collection_status="unavailable",
        view_status="implemented",
        availability_period=DERIVATIVES_LIQUIDATION_SUMMARY_PERIOD,
        unavailable_reason=DERIVATIVES_LIQUIDATION_UNAVAILABLE_REASON,
        limitations=(
            "public liquidation stream is real-time and requires a streaming runtime",
            "stream snapshots include only the largest liquidation order within each 1000ms interval",
            "signed REST force-order query is user data and is outside public market-data scope",
        ),
        downstream_implication=(
            "liquidation evidence is unavailable and must not be treated as neutral risk context"
        ),
    ),
    "open_interest": PublicDataClassCapability(
        data_class="open_interest",
        collection_status="implemented",
        view_status="implemented",
        request_classes=("open_interest_current", "open_interest_history"),
    ),
    "premium_index": PublicDataClassCapability(
        data_class="premium_index",
        collection_status="implemented",
        view_status="implemented",
        request_classes=("premium_index",),
    ),
    "spread_depth": PublicDataClassCapability(
        data_class="spread_depth",
        collection_status="implemented",
        view_status="implemented",
        request_classes=("order_book_depth",),
    ),
}

SUPPORTED_DERIVATIVES_DATA_CLASSES: Final[set[str]] = set(DERIVATIVES_DATA_CLASS_CAPABILITIES)
DERIVATIVES_RAW_DATA_CLASSES: Final[set[str]] = {
    data_class
    for data_class, capability in DERIVATIVES_DATA_CLASS_CAPABILITIES.items()
    if capability.collection_status in {"implemented", "unavailable"}
}
DERIVATIVES_VIEW_DATA_CLASSES: Final[set[str]] = {
    data_class
    for data_class, capability in DERIVATIVES_DATA_CLASS_CAPABILITIES.items()
    if capability.view_status == "implemented"
}
DERIVATIVES_CONTEXT_DATA_CLASSES: Final[set[str]] = set(DERIVATIVES_VIEW_DATA_CLASSES)

SUPPORTED_MACRO_CALENDAR_SOURCES: Final[set[str]] = {"federal_reserve_fomc"}
SUPPORTED_MACRO_CALENDAR_DATA_CLASSES: Final[set[str]] = {"central_bank_event"}
SUPPORTED_MACRO_CALENDAR_REGIONS: Final[set[str]] = {"US"}

SUPPORTED_ONCHAIN_FLOW_SOURCES: Final[set[str]] = {"public_aggregate"}
SUPPORTED_ONCHAIN_FLOW_DATA_CLASSES: Final[set[str]] = {
    "chain_activity",
    "exchange_flow_availability",
    "network_congestion",
    "stablecoin_supply",
}
SUPPORTED_ONCHAIN_FLOW_ASSETS: Final[set[str]] = {"ALL_STABLECOINS", "BTC"}
SUPPORTED_ONCHAIN_FLOW_CHAINS: Final[set[str]] = {"all", "bitcoin"}


def derivatives_data_class_capability(data_class: str) -> PublicDataClassCapability | None:
    return DERIVATIVES_DATA_CLASS_CAPABILITIES.get(data_class)


def unsupported_derivatives_raw_collection_reason(data_class: str, source: str) -> str:
    return f"{data_class} raw collection is not implemented for {source}."


def unsupported_derivatives_view_reason(data_class: str) -> str:
    return f"{data_class} derivatives views are not implemented."
