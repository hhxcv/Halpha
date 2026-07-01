from __future__ import annotations

from html import escape

from halpha.dashboard.assets import dashboard_asset_text
from halpha.dashboard.constants import (
    DEFAULT_DASHBOARD_DISPLAY_TIMEZONE,
    DEFAULT_DASHBOARD_PNL_COLOR_SCHEME,
    DEFAULT_DASHBOARD_TIMESTAMP_DATE_ORDER,
    DEFAULT_DASHBOARD_TIMESTAMP_HOUR_CYCLE,
)


def dashboard_index_html(
    *,
    display_timezone: str = DEFAULT_DASHBOARD_DISPLAY_TIMEZONE,
    pnl_color_scheme: str = DEFAULT_DASHBOARD_PNL_COLOR_SCHEME,
    timestamp_hour_cycle: str = DEFAULT_DASHBOARD_TIMESTAMP_HOUR_CYCLE,
    timestamp_date_order: str = DEFAULT_DASHBOARD_TIMESTAMP_DATE_ORDER,
) -> str:
    display_timezone_attr = escape(display_timezone or DEFAULT_DASHBOARD_DISPLAY_TIMEZONE, quote=True)
    pnl_color_scheme_attr = escape(pnl_color_scheme or DEFAULT_DASHBOARD_PNL_COLOR_SCHEME, quote=True)
    timestamp_hour_cycle_attr = escape(timestamp_hour_cycle or DEFAULT_DASHBOARD_TIMESTAMP_HOUR_CYCLE, quote=True)
    timestamp_date_order_attr = escape(timestamp_date_order or DEFAULT_DASHBOARD_TIMESTAMP_DATE_ORDER, quote=True)
    return (
        dashboard_asset_text("index.html")
        .replace("__HALPHA_DASHBOARD_DISPLAY_TIMEZONE__", display_timezone_attr)
        .replace("__HALPHA_DASHBOARD_PNL_COLOR_SCHEME__", pnl_color_scheme_attr)
        .replace("__HALPHA_DASHBOARD_TIMESTAMP_HOUR_CYCLE__", timestamp_hour_cycle_attr)
        .replace("__HALPHA_DASHBOARD_TIMESTAMP_DATE_ORDER__", timestamp_date_order_attr)
    )
