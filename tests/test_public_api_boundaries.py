from __future__ import annotations

from halpha.macro import macro_calendar_views
from halpha.market import ohlcv_source
from halpha.onchain import onchain_flow_views


def test_audited_test_helpers_are_private() -> None:
    assert not hasattr(macro_calendar_views, "load_macro_calendar_view_records")
    assert hasattr(macro_calendar_views, "_load_macro_calendar_view_records")

    assert not hasattr(onchain_flow_views, "load_onchain_flow_view_records")
    assert hasattr(onchain_flow_views, "_load_onchain_flow_view_records")

    assert not hasattr(ohlcv_source, "fetch_configured_ohlcv")
    assert hasattr(ohlcv_source, "_fetch_configured_ohlcv")
