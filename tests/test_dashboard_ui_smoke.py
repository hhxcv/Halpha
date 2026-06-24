from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from dashboard_asset_helpers import (
    dashboard_css,
    dashboard_dialogs_script,
    dashboard_monitor_script,
    dashboard_reports_script,
    dashboard_script,
    dashboard_shell_html,
    dashboard_strategy_chart_script,
)


EXPECTED_DASHBOARD_VIEWS = {
    "overview",
    "reports",
    "strategies",
    "monitor",
    "intelligence",
    "settings",
}


def test_dashboard_ui_source_sections_are_static_assets() -> None:
    css = dashboard_css()
    script = dashboard_script()
    shell = dashboard_shell_html(css="", script="")

    assert ".reports-layout" in css
    assert ".strategy-layout" in css
    assert "function renderReportLibrary" in script
    assert "function renderSettings" in script
    assert "__HALPHA_DASHBOARD_DISPLAY_TIMEZONE__" in shell
    assert '<link rel="stylesheet" href="/assets/dashboard.css">' in shell
    assert '<script src="/assets/dashboard_shared.js" defer></script>' in shell
    assert '<script src="/assets/dashboard_dialogs.js" defer></script>' in shell
    assert '<script src="/assets/dashboard_reports.js" defer></script>' in shell
    assert '<script src="/assets/dashboard_strategy_chart.js" defer></script>' in shell
    assert '<script src="/assets/dashboard_monitor.js" defer></script>' in shell
    assert '<script src="/assets/dashboard.js" defer></script>' in shell
    assert "<style>" not in shell
    assert "\n  <script>\n" not in shell


def test_dashboard_static_assets_are_served(tmp_path: Path) -> None:
    client = _dashboard_client(tmp_path)

    html = client.get("/")
    css = client.get("/assets/dashboard.css")
    shared_script = client.get("/assets/dashboard_shared.js")
    dialogs_script = client.get("/assets/dashboard_dialogs.js")
    reports_script = client.get("/assets/dashboard_reports.js")
    strategy_chart_script = client.get("/assets/dashboard_strategy_chart.js")
    monitor_script = client.get("/assets/dashboard_monitor.js")
    script = client.get("/assets/dashboard.js")
    missing = client.get("/assets/missing.js")

    assert html.status_code == 200
    assert '<link rel="stylesheet" href="/assets/dashboard.css">' in html.text
    assert '<script src="/assets/dashboard_shared.js" defer></script>' in html.text
    assert '<script src="/assets/dashboard_dialogs.js" defer></script>' in html.text
    assert '<script src="/assets/dashboard_reports.js" defer></script>' in html.text
    assert '<script src="/assets/dashboard_strategy_chart.js" defer></script>' in html.text
    assert '<script src="/assets/dashboard_monitor.js" defer></script>' in html.text
    assert '<script src="/assets/dashboard.js" defer></script>' in html.text
    assert html.text.index("/assets/dashboard_shared.js") < html.text.index("/assets/dashboard_dialogs.js")
    assert html.text.index("/assets/dashboard_dialogs.js") < html.text.index("/assets/dashboard_reports.js")
    assert html.text.index("/assets/dashboard_reports.js") < html.text.index("/assets/dashboard_strategy_chart.js")
    assert html.text.index("/assets/dashboard_strategy_chart.js") < html.text.index("/assets/dashboard_monitor.js")
    assert html.text.index("/assets/dashboard_monitor.js") < html.text.index("/assets/dashboard.js")
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert ".reports-layout" in css.text
    assert shared_script.status_code == 200
    assert shared_script.headers["content-type"].startswith("application/javascript")
    assert "window.HalphaDashboardShared" in shared_script.text
    assert dialogs_script.status_code == 200
    assert dialogs_script.headers["content-type"].startswith("application/javascript")
    assert "window.HalphaDashboardDialogs" in dialogs_script.text
    assert reports_script.status_code == 200
    assert reports_script.headers["content-type"].startswith("application/javascript")
    assert "window.HalphaDashboardReports" in reports_script.text
    assert strategy_chart_script.status_code == 200
    assert strategy_chart_script.headers["content-type"].startswith("application/javascript")
    assert "window.HalphaDashboardStrategyChart" in strategy_chart_script.text
    assert monitor_script.status_code == 200
    assert monitor_script.headers["content-type"].startswith("application/javascript")
    assert "window.HalphaDashboardMonitor" in monitor_script.text
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("application/javascript")
    assert "function renderReportLibrary" in script.text
    assert missing.status_code == 404


class DashboardShellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.nav_targets: set[str] = set()
        self.view_sections: set[str] = set()
        self.data_attrs: set[str] = set()
        self.meta_viewport = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        self.data_attrs.update(key for key in attr_map if key.startswith("data-"))
        if tag == "meta" and attr_map.get("name") == "viewport":
            self.meta_viewport = attr_map.get("content", "")
        target = attr_map.get("data-view-target")
        if target:
            self.nav_targets.add(target)
        view = attr_map.get("data-view")
        classes = set(attr_map.get("class", "").split())
        if view and "view" in classes:
            self.view_sections.add(view)


def test_dashboard_shell_navigation_matches_redesign_views(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    parser = DashboardShellParser()
    parser.feed(html)

    assert parser.meta_viewport == "width=device-width, initial-scale=1"
    assert parser.nav_targets == EXPECTED_DASHBOARD_VIEWS
    assert parser.view_sections == EXPECTED_DASHBOARD_VIEWS
    assert 'href="#artifacts"' not in html
    assert 'href="#commands"' not in html


def test_dashboard_css_contracts_cover_redesigned_desktop_and_small_viewports(tmp_path: Path) -> None:
    css = _style_block(_dashboard_html(tmp_path))

    assert ".app-shell" in css
    assert "grid-template-columns: 224px minmax(0, 1fr);" in css
    assert "height: 100vh;" in css
    assert "overflow: hidden;" in css
    assert ".main-shell" in css
    assert "overflow-y: auto;" in css
    assert ".reports-layout" in css
    assert ".strategy-layout" in css
    assert ".monitor-layout" in css
    assert ".intelligence-layout" in css
    assert ".settings-main" in css
    assert ".kline-panel" in css
    assert ".markdown-reader" in css
    assert "@media (max-width: 1180px)" in css
    assert "@media (max-width: 760px)" in css
    assert "grid-template-columns: 1fr;" in css


def test_dashboard_pages_match_design_reference_roles(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)

    assert "System status, reports, monitor, and data health" in html
    assert "All reports" in html
    assert "Report outline" in html
    assert "Backtest candlestick chart" in html
    assert "Monitor timeline" in html
    assert "Topic volume over time" in html
    assert "Config file" in html
    assert "Storage maintenance" in script
    assert 'class="storage-maintenance settings-storage-page"' in script
    assert "Artifacts" not in _nav_block(html)


def test_dashboard_uses_dropdowns_tabs_and_detail_rails_for_primary_flows(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)

    for selector_id in [
        "strategy-symbol",
        "strategy-timeframe",
        "strategy-name",
        "intel-asset",
        "intel-range",
        "intel-severity",
        "intel-source",
        "intel-sort",
    ]:
        assert f'id="{selector_id}"' in html
    assert 'id="config-profile" class="readonly-value"' in html
    assert 'data-strategy-tab="trades"' in html
    assert 'data-intel-tab="text"' in html
    assert "detail-rail" in html
    assert "fillSelect" in script
    assert "renderOutline" in script
    assert "filteredIntelligenceItems" in script
    assert "withinIntelRange" in script
    assert "severityRank" in script
    assert "resetIntelFilters" in script


def test_dashboard_status_class_covers_nonterminal_states(tmp_path: Path) -> None:
    script = _script_block(_dashboard_html(tmp_path))

    assert '"disabled", "not_generated", "not_run"' in script
    assert 'return "skipped";' in script
    assert '"insufficient_data", "unavailable"' in script
    assert 'return "partial";' in script


def test_dashboard_interaction_hooks_cover_redesigned_workflows(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)
    parser = DashboardShellParser()
    parser.feed(html)

    assert "data-job-intent" in parser.data_attrs
    assert "data-monitor-job" in parser.data_attrs
    assert "data-service-role" in parser.data_attrs
    assert "data-service-action" in parser.data_attrs
    assert "data-view-target" in parser.data_attrs
    assert "data-preview-endpoint" in parser.data_attrs
    assert "data-delete-endpoint" in parser.data_attrs
    assert "data-services-endpoint" in parser.data_attrs
    assert "data-settings-endpoint" in parser.data_attrs
    assert 'document.querySelectorAll("[data-view-target]")' in script
    assert "setHashView(node.dataset.viewTarget)" in script
    assert "selectReport(button.dataset.reportRunId)" in script
    assert "postJob(button.dataset.jobIntent" in script
    assert "serviceAction(button.dataset.serviceRole, button.dataset.serviceAction)" in dashboard_monitor_script()
    assert "startMonitorJob(button.dataset.monitorJob)" in script
    assert "cancelRunningMonitorJobs" not in script
    assert "stop-monitor-button" not in html
    assert "deleteSelectedReport" in script
    assert "cleanup(\"runs\")" in script
    assert "cleanup(\"shared\")" in script
    assert "saveSettings" in script
    assert "backupSettings" in script
    assert "renderStorageMaintenance" in script
    assert "settingFieldIsVisible" in script
    assert "pruneHiddenSettingChanges" in script
    assert "data-setting-path" in script
    assert "unit_interval_number" in script
    assert 'min="0" max="1" step="0.01"' in script
    assert "selectedRunArtifacts" in script
    assert "selectedSharedStores" in script


def test_dashboard_uses_in_app_confirmation_dialogs(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert 'id="dashboard-dialog-backdrop"' in html
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'id="dashboard-dialog-input"' in html
    assert ".dialog-backdrop" in css
    assert ".dialog-actions" in css
    assert "window.HalphaDashboardDialogs" in dashboard_dialogs_script()
    assert "confirmAction" in dashboard_dialogs_script()
    assert "typedConfirmation" in dashboard_dialogs_script()
    assert "wire" in dashboard_dialogs_script()
    assert "const dialogs = window.HalphaDashboardDialogs;" in script
    assert "dialogs.wire();" in script
    assert "dialogs.confirmAction" in script
    assert "dialogs.typedConfirmation" in script
    assert "window.confirm" not in script
    assert "window.prompt" not in script
    assert "window.alert" not in script


def test_dashboard_shell_exposes_configured_display_timezone(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)

    assert 'data-display-timezone="Asia/Shanghai"' in html
    assert '<strong id="display-timezone">Asia/Shanghai</strong>' in html
    assert 'const displayTimezone = app.dataset.displayTimezone || "Asia/Shanghai";' in script
    assert "new Intl.DateTimeFormat" in script
    assert "formatTimestamp(value)" in script
    assert "looksLikeIsoTimestamp(value)" in script


def test_dashboard_startup_event_selectors_exist_in_shell(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)
    ids = set(re.findall(r'id="([^"]+)"', html))
    startup_selectors = set(
        re.findall(r'document\.querySelector\("#([A-Za-z0-9_-]+)"\)\.addEventListener', script)
    )

    assert startup_selectors
    assert startup_selectors <= ids


def test_dashboard_shell_does_not_emit_nul_or_non_ascii_control_characters(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)

    assert "\x00" not in html
    assert not [char for char in html if ord(char) > 127]


def test_dashboard_preview_job_and_monitor_contracts_are_present(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert "renderReportPreview(preview, run)" in script
    assert "markdownToHtml(markdown, state.reportSearchTerm)" in script
    assert "store.source_label" in script
    assert "store.state_scope" in script
    assert "window.HalphaDashboardReports" in dashboard_reports_script()
    assert "createReportHelpers" in dashboard_reports_script()
    assert "const reportsWorkflow = window.HalphaDashboardReports;" in script
    assert "reportHelpers.reportRecords(state.runs)" in script
    assert "isAvailableReport(run)" in dashboard_reports_script()
    assert 'reportState.status === "available"' in script
    assert "run.report_state?.artifact" in script
    assert 'data-report-job="generate"' in html
    assert 'data-job-intent="run_no_codex"' not in html
    assert 'id="overview-report-job-status"' in html
    assert 'id="reports-report-job-status"' in html
    assert ".hidden" in css
    assert "display: none !important;" in css
    assert "startReportJob" in script
    assert 'postJob("run", {confirm_codex: true})' in script
    assert "pollReportJob" in script
    assert "reportJobShouldRender" in script
    assert "Report artifact recorded" not in script
    assert "state.generatedReportRunId" in script
    assert "postJob(intent, params = {})" in script
    assert "renderValidationJob(job)" in script
    assert "window.HalphaDashboardMonitor" in dashboard_monitor_script()
    assert "createMonitorWorkflow" in dashboard_monitor_script()
    assert "const monitorWorkflowModule = window.HalphaDashboardMonitor;" in script
    assert "monitorWorkflow.wire();" in script
    assert "startMonitorJob(intent)" in dashboard_monitor_script()
    assert "enableDailyReport" in dashboard_monitor_script()
    assert "renderMonitor()" in dashboard_monitor_script()
    assert "renderMonitorAlertsTable" in dashboard_monitor_script()
    assert "renderMonitorJobsTable" in dashboard_monitor_script()
    assert "serviceAction(role, action)" in dashboard_monitor_script()
    assert "Monitor last error" in dashboard_monitor_script()
    assert "Schedule last error" in dashboard_monitor_script()
    assert "Latest schedule dispatch" in dashboard_monitor_script()
    assert "Daily report authorization" in dashboard_monitor_script()
    assert 'data-service-role="monitor"' in html
    assert 'data-service-role="schedule"' in html
    assert 'data-service-action="restart"' in html


def test_dashboard_strategy_backtest_chart_shell_contracts_are_present(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert ".kline-panel" in css
    assert ".chart-wrap" in css
    assert "height: 52vh;" in css
    assert "backtestVisualization(item)" in script
    assert 'strategyChart.renderCandlestickSvg("#backtest-chart", vis)' in script
    assert "renderTradeMarker" in dashboard_strategy_chart_script()
    assert "downloadSelectedOhlcv" in script
    assert "sampleVisualization" not in script
    assert "sampleIntelItems" not in script
    assert 'id="strategy-range"' in html
    assert "chart-tools" in html
    assert "tool-dot" in html
    assert "data-strategy-window" in html
    assert "applyStrategyWindow" in script
    assert "setStrategyWindow" in script
    assert ">USDT</span>" not in html
    assert "Latest available window" not in html
    assert "Backtest candlestick chart" in html


def test_dashboard_shell_has_no_unwired_dashboard_controls_or_fabricated_sources(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)

    assert 'id="report-reader-search"' in html
    assert "state.reportSearchTerm" in script
    assert "renderInline" in script
    assert "Report content is not available yet" not in script
    assert '"Run manifest"' not in script
    assert '"Report artifact"' not in script
    assert '["BTC", "ETH", "USDT", "SOL", "XRP", "ADA"]' not in script
    assert "{max_cycles: 72, interval_seconds: 360}" not in script
    assert "monitor_loop" not in html
    assert "monitor_loop" not in script
    assert "state.monitor?.settings" in script
    assert '"#intel-asset", "#intel-range", "#intel-severity", "#intel-source", "#intel-sort"' in script


def _dashboard_html(tmp_path: Path) -> str:
    client = _dashboard_client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    return response.text


def _dashboard_client(tmp_path: Path) -> TestClient:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    return TestClient(create_dashboard_app(config, config_path=config_path))


def _style_block(html: str) -> str:
    if "<style>" not in html:
        return dashboard_css()
    start = html.index("<style>") + len("<style>")
    end = html.index("</style>", start)
    return html[start:end]


def _script_block(html: str) -> str:
    if "<script>" not in html:
        return dashboard_script()
    start = html.index("<script>") + len("<script>")
    end = html.index("</script>", start)
    return html[start:end]


def _nav_block(html: str) -> str:
    start = html.index('<nav class="nav">')
    end = html.index("</nav>", start)
    return html[start:end]


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: false
  sources: []
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path
