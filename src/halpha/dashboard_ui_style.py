from __future__ import annotations

from .dashboard_assets import dashboard_asset_text


def dashboard_css() -> str:
    return dashboard_asset_text("dashboard.css")
