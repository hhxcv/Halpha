from __future__ import annotations

from html import escape

from halpha.dashboard.assets import dashboard_asset_text


DEFAULT_DASHBOARD_DISPLAY_TIMEZONE = "Asia/Shanghai"


def dashboard_index_html(*, display_timezone: str = DEFAULT_DASHBOARD_DISPLAY_TIMEZONE) -> str:
    display_timezone_attr = escape(display_timezone or DEFAULT_DASHBOARD_DISPLAY_TIMEZONE, quote=True)
    return dashboard_asset_text("index.html").replace(
        "__HALPHA_DASHBOARD_DISPLAY_TIMEZONE__",
        display_timezone_attr,
    )
