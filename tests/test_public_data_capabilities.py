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
    SUPPORTED_DERIVATIVES_DATA_CLASSES as DECLARED_DERIVATIVES_DATA_CLASSES,
    SUPPORTED_DERIVATIVES_MARKET_SOURCES as DECLARED_DERIVATIVES_MARKET_SOURCES,
    SUPPORTED_MACRO_CALENDAR_DATA_CLASSES as DECLARED_MACRO_CALENDAR_DATA_CLASSES,
    SUPPORTED_ONCHAIN_FLOW_DATA_CLASSES as DECLARED_ONCHAIN_FLOW_DATA_CLASSES,
    derivatives_data_class_capability,
)


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
