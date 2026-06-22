from __future__ import annotations

from html import escape

from .dashboard_ui_script import dashboard_script
from .dashboard_ui_shell import dashboard_shell_html
from .dashboard_ui_style import dashboard_css


DEFAULT_DASHBOARD_DISPLAY_TIMEZONE = "Asia/Shanghai"


def dashboard_index_html(*, display_timezone: str = DEFAULT_DASHBOARD_DISPLAY_TIMEZONE) -> str:
    display_timezone_attr = escape(display_timezone or DEFAULT_DASHBOARD_DISPLAY_TIMEZONE, quote=True)
    return dashboard_shell_html(css=dashboard_css(), script=dashboard_script()).replace(
        "__HALPHA_DASHBOARD_DISPLAY_TIMEZONE__",
        display_timezone_attr,
    )
