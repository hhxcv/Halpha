from __future__ import annotations

from halpha.config import (
    SUPPORTED_DERIVATIVES_DATA_CLASSES,
    SUPPORTED_DERIVATIVES_MARKET_SOURCES,
    SUPPORTED_MACRO_CALENDAR_DATA_CLASSES,
    SUPPORTED_ONCHAIN_FLOW_DATA_CLASSES,
)
from halpha.data.public_capabilities import (
    DERIVATIVES_DATA_CLASS_CAPABILITIES,
    DERIVATIVES_LIQUIDATION_SUMMARY_PERIOD,
    MACRO_CALENDAR_CONTEXT_DATA_CLASSES,
    MACRO_CALENDAR_RAW_DATA_CLASSES,
    MACRO_CALENDAR_VIEW_DATA_CLASSES,
    ONCHAIN_FLOW_CONTEXT_DATA_CLASSES,
    ONCHAIN_FLOW_EXCHANGE_FLOW_UNAVAILABLE_REASON,
    ONCHAIN_FLOW_RAW_DATA_CLASSES,
    ONCHAIN_FLOW_VIEW_DATA_CLASSES,
    SUPPORTED_DERIVATIVES_DATA_CLASSES as DECLARED_DERIVATIVES_DATA_CLASSES,
    SUPPORTED_DERIVATIVES_MARKET_SOURCES as DECLARED_DERIVATIVES_MARKET_SOURCES,
    SUPPORTED_MACRO_CALENDAR_DATA_CLASSES as DECLARED_MACRO_CALENDAR_DATA_CLASSES,
    SUPPORTED_ONCHAIN_FLOW_DATA_CLASSES as DECLARED_ONCHAIN_FLOW_DATA_CLASSES,
    derivatives_data_class_capability,
    macro_calendar_data_class_capability,
    onchain_flow_data_class_capability,
    unsupported_macro_calendar_raw_collection_reason,
    unsupported_macro_calendar_view_reason,
    unsupported_onchain_flow_raw_collection_reason,
    unsupported_onchain_flow_view_reason,
)
from halpha.macro.macro_calendar_context import SUPPORTED_DATA_CLASSES as MACRO_CALENDAR_CONTEXT_SUPPORTED
from halpha.macro.macro_calendar_views import SUPPORTED_VIEW_DATA_CLASSES as MACRO_CALENDAR_VIEW_SUPPORTED
from halpha.onchain.onchain_flow_context import SUPPORTED_DATA_CLASSES as ONCHAIN_FLOW_CONTEXT_SUPPORTED
from halpha.onchain.onchain_flow_views import SUPPORTED_VIEW_DATA_CLASSES as ONCHAIN_FLOW_VIEW_SUPPORTED


def test_config_uses_public_data_capability_declarations() -> None:
    assert SUPPORTED_DERIVATIVES_MARKET_SOURCES == DECLARED_DERIVATIVES_MARKET_SOURCES
    assert SUPPORTED_DERIVATIVES_DATA_CLASSES == DECLARED_DERIVATIVES_DATA_CLASSES
    assert SUPPORTED_MACRO_CALENDAR_DATA_CLASSES == DECLARED_MACRO_CALENDAR_DATA_CLASSES
    assert SUPPORTED_ONCHAIN_FLOW_DATA_CLASSES == DECLARED_ONCHAIN_FLOW_DATA_CLASSES


def test_derivatives_liquidation_capability_records_public_limitation() -> None:
    capability = derivatives_data_class_capability("liquidation_summary")

    assert capability is DERIVATIVES_DATA_CLASS_CAPABILITIES["liquidation_summary"]
    assert capability.collection_status == "unavailable"
    assert capability.view_status == "implemented"
    assert capability.availability_period == DERIVATIVES_LIQUIDATION_SUMMARY_PERIOD
    assert capability.unavailable_reason is not None
    assert "unauthenticated REST liquidation summaries are not available" in capability.unavailable_reason
    assert capability.downstream_implication is not None
    assert "must not be treated as neutral" in capability.downstream_implication


def test_macro_calendar_capability_drives_raw_view_and_context_support() -> None:
    capability = macro_calendar_data_class_capability("central_bank_event")
    economic_release = macro_calendar_data_class_capability("economic_release")

    assert capability is not None
    assert capability.collection_status == "implemented"
    assert capability.view_status == "implemented"
    assert economic_release is not None
    assert economic_release.collection_status == "implemented"
    assert economic_release.view_status == "implemented"
    assert MACRO_CALENDAR_RAW_DATA_CLASSES == {"central_bank_event", "economic_release"}
    assert MACRO_CALENDAR_VIEW_DATA_CLASSES == MACRO_CALENDAR_VIEW_SUPPORTED
    assert MACRO_CALENDAR_CONTEXT_DATA_CLASSES == MACRO_CALENDAR_CONTEXT_SUPPORTED
    assert unsupported_macro_calendar_raw_collection_reason(
        "central_bank_event",
        "other_source",
    ) == "other_source macro/calendar collection is not implemented."
    assert unsupported_macro_calendar_view_reason("future_event") == "future_event macro calendar views are not implemented."


def test_onchain_flow_capability_drives_raw_view_and_context_support() -> None:
    capability = onchain_flow_data_class_capability("exchange_flow_availability")

    assert capability is not None
    assert capability.collection_status == "unavailable"
    assert capability.view_status == "implemented"
    assert capability.unavailable_reason == ONCHAIN_FLOW_EXCHANGE_FLOW_UNAVAILABLE_REASON
    assert capability.limitations
    assert capability.downstream_implication is not None
    assert "must not be treated as neutral" in capability.downstream_implication
    assert ONCHAIN_FLOW_RAW_DATA_CLASSES == DECLARED_ONCHAIN_FLOW_DATA_CLASSES
    assert ONCHAIN_FLOW_VIEW_DATA_CLASSES == ONCHAIN_FLOW_VIEW_SUPPORTED
    assert ONCHAIN_FLOW_CONTEXT_DATA_CLASSES == ONCHAIN_FLOW_CONTEXT_SUPPORTED
    assert unsupported_onchain_flow_raw_collection_reason(
        "stablecoin_supply",
        "other_source",
    ) == "other_source on-chain flow collection is not implemented."
    assert unsupported_onchain_flow_view_reason("future_flow") == "future_flow on-chain flow views are not implemented."
