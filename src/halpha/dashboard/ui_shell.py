from __future__ import annotations

from halpha.dashboard.assets import dashboard_asset_text


def dashboard_shell_html(*, css: str, script: str) -> str:
    html = dashboard_asset_text("index.html")
    if css:
        html = html.replace(
            '<link rel="stylesheet" href="/assets/dashboard.css">',
            f"<style>\n{css}  </style>",
        )
    if script:
        html = html.replace(
            '<script src="/assets/dashboard.js" defer></script>',
            f"<script>\n{script}  </script>",
        )
    return html
