from __future__ import annotations

from halpha.dashboard.assets import dashboard_asset_text


def dashboard_css() -> str:
    return dashboard_asset_text("dashboard.css")


def dashboard_shared_script() -> str:
    return dashboard_asset_text("dashboard_shared.js")


def dashboard_script() -> str:
    return f"{dashboard_shared_script()}\n{dashboard_asset_text('dashboard.js')}"


def dashboard_shell_html(*, css: str, script: str) -> str:
    html = dashboard_asset_text("index.html")
    if css:
        html = html.replace(
            '<link rel="stylesheet" href="/assets/dashboard.css">',
            f"<style>\n{css}  </style>",
        )
    if script:
        script_tags = (
            '  <script src="/assets/dashboard_shared.js" defer></script>\n'
            '  <script src="/assets/dashboard.js" defer></script>'
        )
        html = html.replace(
            script_tags,
            f"<script>\n{script}  </script>",
        )
    return html
