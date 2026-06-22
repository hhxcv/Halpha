from __future__ import annotations

from halpha.dashboard.assets import dashboard_asset_text


def dashboard_script() -> str:
    return dashboard_asset_text("dashboard.js")
