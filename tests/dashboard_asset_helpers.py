from __future__ import annotations

from halpha.dashboard.assets import dashboard_asset_text


ASSET_VERSION_QUERY = "?v=20260702-macro-tabs"


def dashboard_css() -> str:
    return dashboard_asset_text("dashboard.css")


def dashboard_shared_script() -> str:
    return dashboard_asset_text("dashboard_shared.js")


def dashboard_dialogs_script() -> str:
    return dashboard_asset_text("dashboard_dialogs.js")


def dashboard_reports_script() -> str:
    return dashboard_asset_text("dashboard_reports.js")


def dashboard_strategy_chart_script() -> str:
    return dashboard_asset_text("dashboard_strategy_chart.js")


def dashboard_live_script() -> str:
    return dashboard_asset_text("dashboard_live.js")


def dashboard_data_viewer_script() -> str:
    return dashboard_asset_text("dashboard_data_viewer.js")


def dashboard_script() -> str:
    return "\n".join(
        [
            dashboard_shared_script(),
            dashboard_dialogs_script(),
            dashboard_reports_script(),
            dashboard_strategy_chart_script(),
            dashboard_live_script(),
            dashboard_data_viewer_script(),
            dashboard_asset_text("dashboard.js"),
        ]
    )


def dashboard_shell_html(*, css: str, script: str) -> str:
    html = dashboard_asset_text("index.html")
    if css:
        html = html.replace(
            f'<link rel="stylesheet" href="/assets/dashboard.css{ASSET_VERSION_QUERY}">',
            f"<style>\n{css}  </style>",
        )
    if script:
        script_tags = (
            f'  <script src="/assets/dashboard_shared.js{ASSET_VERSION_QUERY}" defer></script>\n'
            f'  <script src="/assets/dashboard_dialogs.js{ASSET_VERSION_QUERY}" defer></script>\n'
            f'  <script src="/assets/dashboard_reports.js{ASSET_VERSION_QUERY}" defer></script>\n'
            f'  <script src="/assets/dashboard_strategy_chart.js{ASSET_VERSION_QUERY}" defer></script>\n'
            f'  <script src="/assets/dashboard_live.js{ASSET_VERSION_QUERY}" defer></script>\n'
            f'  <script src="/assets/dashboard_data_viewer.js{ASSET_VERSION_QUERY}" defer></script>\n'
            f'  <script src="/assets/dashboard.js{ASSET_VERSION_QUERY}" defer></script>'
        )
        html = html.replace(
            script_tags,
            f"<script>\n{script}  </script>",
        )
    return html
