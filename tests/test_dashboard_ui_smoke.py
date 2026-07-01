from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from dashboard_asset_helpers import (
    dashboard_css,
    dashboard_reports_script,
    dashboard_script,
    dashboard_strategy_chart_script,
)


EXPECTED_DASHBOARD_VIEWS = {
    "overview",
    "reports",
    "strategies",
    "live",
    "intelligence",
    "settings",
}


REQUIRED_SCRIPT_ASSETS = (
    "/assets/dashboard_shared.js",
    "/assets/dashboard_dialogs.js",
    "/assets/dashboard_reports.js",
    "/assets/dashboard_strategy_chart.js",
    "/assets/dashboard_live.js",
    "/assets/dashboard_data_viewer.js",
    "/assets/dashboard.js",
)


def test_dashboard_static_assets_are_served_from_external_files(tmp_path: Path) -> None:
    client = _dashboard_client(tmp_path)

    html = client.get("/")
    css = client.get("/assets/dashboard.css")
    scripts = {asset: client.get(asset) for asset in REQUIRED_SCRIPT_ASSETS}
    missing = client.get("/assets/missing.js")

    assert html.status_code == 200
    assert html.text.count('<link rel="stylesheet" href="/assets/dashboard.css">') == 1
    assert '<link rel="stylesheet" href="/assets/dashboard.css">' in html.text
    for asset in REQUIRED_SCRIPT_ASSETS:
        assert html.text.count(f'<script src="{asset}" defer></script>') == 1
    script_positions = [html.text.index(asset) for asset in REQUIRED_SCRIPT_ASSETS]
    assert script_positions == sorted(script_positions)
    assert "<style>" not in html.text
    assert "<script>" not in html.text
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert ".reports-layout" in css.text
    for response in scripts.values():
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/javascript")
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

    for selector in (
        ".app-shell",
        ".sidebar",
        ".main-shell",
        ".reports-layout",
        ".strategy-layout",
        ".live-layout",
        ".intelligence-layout",
        ".settings-main",
        ".kline-panel",
        ".markdown-reader",
        ".detail-rail",
    ):
        assert selector in css
    assert "@media (max-width: 1180px)" in css
    assert "@media (max-width: 760px)" in css


def test_dashboard_pages_expose_primary_semantic_views(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    parser = DashboardShellParser()
    parser.feed(html)

    assert parser.nav_targets == EXPECTED_DASHBOARD_VIEWS
    assert parser.view_sections == EXPECTED_DASHBOARD_VIEWS
    assert "Artifacts" not in _nav_block(html)


def test_dashboard_shell_uses_live_status_without_local_mode_badges(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert "System healthy" not in html
    assert "Local mode" not in html
    assert "No data leaves this device through the dashboard UI." not in html
    assert 'id="sidebar-live-dot"' in html
    assert 'id="sidebar-live-title">Live status</span>' in html
    assert 'id="sidebar-live-text">Loading Live status.</div>' in html
    assert "liveSidebarState" in script
    assert "renderSidebarLiveStatus" in script
    assert "Live collection and scheduled review are enabled." in script
    assert "loadLivePayload().catch(() => renderSidebarLiveStatus())" in script
    assert ".health-dot.stopped" in css
    assert ".health-dot.unknown" in css


@pytest.mark.parametrize(
    "selector_id",
    [
        "strategy-symbol",
        "strategy-timeframe",
        "strategy-name",
        "intel-collect-range",
        "intel-preview-range",
    ],
)
def test_dashboard_exposes_primary_filter_controls(tmp_path: Path, selector_id: str) -> None:
    html = _dashboard_html(tmp_path)

    assert f'id="{selector_id}"' in html


@pytest.mark.parametrize(
    "contract",
    [
        'data-strategy-tab="equity"',
        'data-intel-tab="overview"',
        'data-intel-tab="text_event"',
        'data-intel-tab="macro_calendar"',
        'data-intel-tab="onchain_flow"',
        'data-intel-tab="derivatives_market"',
        "detail-rail",
    ],
)
def test_dashboard_exposes_tabs_and_detail_rails_for_primary_flows(tmp_path: Path, contract: str) -> None:
    html = _dashboard_html(tmp_path)

    assert 'id="settings-config-select"' in html
    assert contract in html


def test_dashboard_status_class_covers_nonterminal_states(tmp_path: Path) -> None:
    script = _script_block(_dashboard_html(tmp_path))

    assert '"disabled", "not_generated", "not_run"' in script
    assert 'return "skipped";' in script
    assert '"insufficient_data", "unavailable"' in script
    assert 'return "partial";' in script
    assert '"created", "creating", "queued"' in script
    assert 'return "pending";' in script


def test_dashboard_report_job_controls_expose_dom_contracts(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    parser = DashboardShellParser()
    parser.feed(html)

    assert "data-preview-endpoint" in parser.data_attrs
    assert 'data-report-job="generate"' in html
    assert 'id="topbar-report-generate"' in html
    assert 'id="download-report-button"' not in html
    assert 'id="report-details-button"' in html
    assert 'id="report-details-drawer"' in html
    assert 'id="report-details-drawer-body"' in html
    assert 'id="overview-report-job-status"' in html
    assert 'id="reports-report-job-status"' in html
    assert "Daily Market Brief ${run.run_id}" not in dashboard_reports_script()


def test_dashboard_data_viewer_controls_expose_dom_contracts(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    parser = DashboardShellParser()
    parser.feed(html)

    for data_attr in (
        "data-data-viewer-summary-endpoint",
        "data-data-viewer-timeline-endpoint",
        "data-data-viewer-preview-endpoint",
        "data-data-viewer-export-endpoint",
        "data-data-viewer-collect-plan-endpoint",
        "data-data-viewer-collect-jobs-endpoint",
    ):
        assert data_attr in parser.data_attrs
    for selector_id in (
        "strategy-workbench",
        "strategy-operation-tabs",
        "strategy-profile-overview",
        "strategy-backtest-board",
        "strategy-backtest-detail",
        "strategy-backtest-back",
        "strategy-detail-title",
        "strategy-detail-kicker",
        "strategy-backtest-dialog-backdrop",
        "strategy-backtest-dialog",
        "strategy-profile",
        "strategy-profile-summary",
        "strategy-backtest-range",
        "strategy-backtest-date-range",
        "strategy-backtest-start",
        "strategy-backtest-end",
        "strategy-backtest-submit",
        "strategy-symbol",
        "strategy-timeframe",
        "strategy-name",
        "strategy-evaluation-window",
        "strategy-ohlcv-source-options",
        "strategy-backtest-progress",
        "strategy-experiment-results",
        "strategy-optimize-profile",
        "strategy-optimize-profile-summary",
        "strategy-optimize-results",
        "strategy-chart-source",
        "strategy-chart-symbol",
        "strategy-chart-timeframe",
        "strategy-chart-range",
        "intel-overview-panel",
        "intel-overview-kpis",
        "intel-overview-content",
        "intel-data-viewer",
        "intel-data-type",
        "intel-collect-open",
        "intel-collect-dialog-backdrop",
        "intel-collect-dialog",
        "intel-collect-dialog-title",
        "intel-collect-dialog-close",
        "intel-collect-dialog-cancel",
        "intel-collect-range",
        "intel-collect-date-range",
        "intel-collect-start",
        "intel-collect-end",
        "intel-collect-reset",
        "intel-preview-range",
        "intel-preview-date-range",
        "intel-preview-start",
        "intel-preview-end",
        "intel-preview-category-filter",
        "intel-preview-keyword",
        "intel-preview-clear-filters",
        "intel-preview-apply-filters",
        "intel-properties-drawer-backdrop",
        "intel-properties-drawer",
        "intel-properties-drawer-title",
        "intel-properties-drawer-close",
        "intel-properties-drawer-body",
        "intel-data-coverage",
        "intel-data-preview-panel",
        "intel-data-job-panel",
    ):
        assert f'id="{selector_id}"' in html
    assert "Identity filter key" not in html
    assert "Identity filter value" not in html
    assert "Source scope" not in html
    assert "Point-in-time view" not in html
    assert "Point-in-time help" not in html
    assert "Optional no-lookahead cutoff" not in html
    assert "Filter" in html
    assert "Date range" in html
    assert "Preview time window" not in html
    assert "Apply filters" not in html
    assert "Clear filters" not in html
    assert 'id="intel-preview-filter-count"' not in html
    assert ">Apply</button>" in html
    assert ">Clear</button>" in html
    assert "Reset preview" not in html
    assert '<h3 class="subsection-title">Preview</h3>' not in html
    assert 'id="intel-properties-button"' not in html
    assert html.count("data-date-range-picker") == 3
    assert html.count("data-range-picker-label") == 3
    assert 'data-data-viewer-action="intel-collect"' in html
    assert 'data-data-viewer-action="strategy-collect"' not in html
    assert 'data-data-viewer-action="strategy-timeline"' not in html
    assert 'id="strategy-collect-preview"' not in html
    assert 'id="strategy-collect-plan"' not in html
    assert 'data-strategy-operation-tab="collect"' not in html
    assert 'data-strategy-operation-tab="export"' not in html
    for removed_id in (
        "intel-asset",
        "intel-range",
        "intel-severity",
        "intel-sort",
        "intel-data-format",
        "intel-data-keyword",
        "intel-data-timeline",
        "intel-data-preview",
        "intel-data-plan",
        "intel-data-export",
        "intel-data-plan-panel",
        "intel-events",
        "intel-detail",
    ):
        assert f'id="{removed_id}"' not in html


def test_dashboard_data_viewer_script_uses_backend_viewer_contracts(tmp_path: Path) -> None:
    script = _script_block(_dashboard_html(tmp_path))

    assert "HalphaDashboardDataViewer" in script
    assert "dataViewerSummary: app.dataset.dataViewerSummaryEndpoint" in script
    assert "dataViewerTimeline: app.dataset.dataViewerTimelineEndpoint" in script
    assert "dataViewerPreview: app.dataset.dataViewerPreviewEndpoint" in script
    assert "dataViewerExport: app.dataset.dataViewerExportEndpoint" in script
    assert "dataViewerCollectPlan: app.dataset.dataViewerCollectPlanEndpoint" in script
    assert "dataViewerCollectJobs: app.dataset.dataViewerCollectJobsEndpoint" in script
    assert "postJson(endpoints.dataViewerTimeline" in script
    assert "postJson(endpoints.dataViewerPreview" in script
    assert "postJson(endpoints.dataViewerCollectPlan" in script
    assert "postJson(endpoints.dataViewerCollectJobs" in script
    assert "postJson(endpoints.dataViewerExport" in script
    assert "renderStrategyOhlcvPreview(payload, request)" in script
    assert 'scope === "strategy" && payload.data_type === "ohlcv"' in script
    assert "Loaded ${escapeHtml(formatNumber(records.length))} bounded candles into the Strategy chart." in script
    assert "runStrategyCollectBatch" in script
    assert "renderStrategyExperimentResults" in script
    assert "renderStrategyOptimizeResults" in script
    assert "renderCollectTimelineResults" in script
    assert "openStrategyBacktestDialog" in script
    assert "strategyProfiles" in script
    assert "renderOperationProgress" in script
    assert "renderIntelligenceOverview" in script
    assert "loadIntelligenceOverviewPreviews" in script
    assert "intelligenceOverviewPreviewRequest" in script
    assert "renderIntelOverviewSparkline" in script
    assert "wireIntelligenceOverviewSparklineHover" in script
    assert 'class="intel-overview-spark-hit" tabindex="0"' in script
    assert "Latest intelligence" in script
    assert "Anomaly radar" in script
    assert "High-impact events" not in script
    assert "loadIntelligenceDataPanels" in script
    assert "renderIntelligenceTimeline" in script
    assert "renderIntelligencePreview" in script
    assert "renderDateJumpCalendar" in script
    assert "previewListItemsWithDates" in script
    assert "recordMetricFacts" in script
    assert "intelPreviewDisplayLimit" in script
    assert "intel-preview-keyword" in script
    assert "intel-preview-category-filter" in script
    assert "syncIntelligencePreviewFilterControls" in script
    assert "refreshIntelligencePreviewFromState" in script
    assert "openIntelligenceCollectDialog" in script
    assert "closeIntelligenceCollectDialog" in script
    assert "recordCategory" in script
    assert "Unclassified" in script
    assert "wireDateRangePickers" in script
    assert "data-range-day" in script
    assert "range-start" in script
    assert "range-end" in script
    assert "in-range" in script
    assert "data-range-quick" in script
    assert "syncDateRangePicker" in script
    assert "Click two dates to set one UTC range." not in script
    assert "ensureStrategyDefaultRange" in script
    assert "coverage.range_start" in script
    assert 'ensureDefaultRange("strategy-data")' in script
    assert 'function wire() {\n          ensureDefaultRange("strategy-data");' not in script
    for status in (
        "collected",
        "no_data",
        "partial",
        "failed",
        "not_collected",
        "stale",
        "warning",
        "error",
        "unsupported",
        "unavailable",
        "unknown",
    ):
        assert f'"{status}"' in script
    assert "Coverage ${kind === \"warning\" ? \"warning\" : \"failed\"}" in script
    assert "Check the timeline to distinguish no_data from not_collected, partial, failed, stale, or unknown coverage." in script


def test_dashboard_live_view_removes_monitor_service_controls_from_user_workflow(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    parser = DashboardShellParser()
    parser.feed(html)

    assert "data-monitor-job" not in parser.data_attrs
    assert "data-service-role" not in parser.data_attrs
    assert "data-service-action" not in parser.data_attrs
    assert 'data-service-role="monitor"' not in html
    assert 'data-service-role="schedule"' not in html
    assert 'data-service-action="restart"' not in html
    assert 'href="#live" data-view-target="live"' in html
    assert 'href="#monitor" data-view-target="monitor"' not in html
    assert 'id="live-view"' in html
    assert 'id="monitor-view"' not in html
    assert "dashboard_monitor.js" not in html
    assert "dashboard_live.js" in html
    assert "Start Monitor" not in html
    assert "Stop Monitor" not in html
    assert "Restart Monitor" not in html
    assert "cancelRunningMonitorJobs" not in _script_block(html)
    assert "stop-monitor-button" not in html


def test_dashboard_storage_and_settings_controls_expose_dom_contracts(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)
    parser = DashboardShellParser()
    parser.feed(html)

    assert "data-delete-endpoint" in parser.data_attrs
    assert "data-services-endpoint" in parser.data_attrs
    assert "data-settings-endpoint" in parser.data_attrs
    assert "data-config-select-endpoint" in parser.data_attrs
    assert "data-config-import-endpoint" in parser.data_attrs
    assert 'id="settings-config-select"' in html
    assert 'id="settings-config-browse"' in html
    assert 'id="settings-config-file-input"' in html
    assert 'id="settings-config-error"' in html
    assert 'id="settings-load-config"' not in html
    assert 'id="settings-valid-pill"' not in html
    assert 'id="settings-last-validated"' not in html
    assert 'data-job-intent="validate"' not in html
    assert "Change summary" not in html
    assert "Validation results" not in html
    assert "data-setting-path" in script
    assert "dashboard.pnl_color_scheme" in script
    assert "dashboard.timestamp_hour_cycle" in script
    assert "dashboard.timestamp_date_order" in script
    assert 'min="0" max="1" step="0.01"' in script
    assert "renderSettingsConfigSelector" in script
    assert "loadSelectedConfigCandidate" in script
    assert "importSelectedConfigFile" in script
    assert "fieldErrorsFromMessages" in script
    assert "setting-control-stack" in script
    assert ".toast.error" in css
    assert ".settings-config-picker" in css
    assert ".field-error" in css
    assert "body[data-theme=\"solar\"] .settings-nav button.active" in css
    assert "body[data-theme=\"solar\"] .settings-nav button.active .settings-nav-chevron" in css
    assert "body[data-theme=\"solar\"] .choice-check::after" in css
    assert "body[data-theme=\"solar\"] input:checked + .choice-check" in css
    assert "body[data-theme=\"solar\"] .choice-chip:has(input:checked)" in css


def test_dashboard_surface_text_has_global_overflow_guards(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)

    assert ".attention-item" in css
    assert ".compact-row" in css
    assert ".strategy-eval-panel" in css
    assert ".intel-store-card" in css
    assert "overflow-wrap: anywhere;" in css
    assert ".toolbar-actions > *" in css
    assert ".control-grid > *" in css
    assert ".control-grid .ghost-button" in css
    assert ".toolbar-actions .primary-button" in css
    assert "body[data-theme=\"solar\"] .control-grid .ghost-button" in css


def test_dashboard_intelligence_overview_is_reader_oriented(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert ".intel-overview-pulse" in css
    assert ".intel-overview-dashboard" in css
    assert ".intel-overview-record-row" in css
    assert ".intel-overview-agenda-row > .tag-row" in css
    assert ".intel-overview-sparkline" in css
    assert ".intel-overview-spark-point.hovered .intel-overview-spark-hover" in css
    assert ".intel-overview-spark-cross.horizontal" in css
    assert 'class="intel-overview-kpis" id="intel-overview-kpis"' in html
    assert 'class="summary-strip" id="intel-overview-kpis"' not in html
    assert "renderIntelOverviewTextEvents" in script
    assert "renderIntelOverviewMacroAgenda" in script
    assert "renderIntelOverviewAnomalyRadar" in script
    assert "renderIntelOverviewChartSection" in script
    assert "data-intel-overview-open" in script
    assert "Shared store coverage" not in script
    assert "Recent intelligence artifacts" not in script


def test_dashboard_overview_report_metrics_use_spaced_cards(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)

    assert 'id="overview-report-metrics" class="report-metrics"' in html
    assert ".report-metrics" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));" in css
    assert "gap: 10px;" in css
    assert "padding: 8px;" in css
    assert ".report-metric" in css
    assert "padding: 14px;" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));" in css


def test_dashboard_dynamic_views_have_skeleton_loading_contracts(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert ".skeleton" in css
    assert "@keyframes skeleton-shimmer" in css
    assert "--skeleton-shimmer-duration: 2.4s;" in css
    assert "animation: skeleton-shimmer var(--skeleton-shimmer-duration) var(--ease-standard) infinite;" in css
    assert "body[data-theme=\"solar\"] .skeleton" in css
    assert "animation: none !important;" in css
    assert ".loading-surface" in css
    assert "renderInitialLoadingPlaceholders()" in script
    assert "renderOverviewLoading()" in script
    assert "renderReportsLoading()" in script
    assert "renderStrategiesLoading()" in script
    assert "renderLiveLoading()" in script
    assert 'setHtml("#live-intelligence-strip", skeletonCards(6, "live-intel-card"));' in script
    assert "renderIntelligenceLoading()" in script
    assert "renderSettingsLoading()" in script
    assert "VIEW_REFRESH_TTL_MS = 15000" in script
    assert "state.viewRefreshPromises[view]" in script


def test_dashboard_layout_composition_containers_are_unframed(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)

    assert "body[data-theme=\"solar\"] .strategy-operation-panel,\n    body[data-theme=\"solar\"] .intel-overview-panel" in css
    assert "background: transparent;" in css
    assert "box-shadow: none;" in css


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
    assert "window.confirm" not in script
    assert "window.prompt" not in script
    assert "window.alert" not in script


def test_dashboard_shell_exposes_configured_display_timezone(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)

    assert 'data-display-timezone="Asia/Shanghai"' in html
    assert 'data-pnl-color-scheme="green_profit_red_loss"' in html
    assert 'data-timestamp-hour-cycle="24h"' in html
    assert 'data-timestamp-date-order="year_first"' in html
    assert 'id="display-timezone"' not in html
    assert 'id="config-ref"' not in html
    assert "Timezone:" not in html
    assert "Config:" not in html
    assert 'id="global-page-title">Overview</h1>' in html
    assert 'id="global-page-subtitle"' not in html
    assert 'class="topbar-secondary"' in html
    assert 'class="topbar-actions"' in html
    assert 'id="global-refresh"' not in html
    assert "VIEW_TITLES" in script
    assert "renderGlobalTopbar" in script
    assert 'let displayTimezone = app.dataset.displayTimezone || "Asia/Shanghai";' in script
    assert 'let pnlColorScheme = app.dataset.pnlColorScheme || "green_profit_red_loss";' in script
    assert "app.dataset.timestampHourCycle" in script
    assert "app.dataset.timestampDateOrder" in script
    assert "applyTimestampDisplayOptionsFromProfile" in script
    assert "applyPnlColorScheme" in script
    assert "new Intl.DateTimeFormat" in script
    assert "formatTimestamp(value)" in script
    assert "looksLikeIsoTimestamp(value)" in script


def test_dashboard_topbar_tabs_and_sidebar_are_interactive_shell_controls(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert 'id="brand-logo-toggle"' in html
    assert 'id="sidebar-collapse-toggle"' in html
    assert 'aria-label="Collapse navigation"' in html
    assert "--global-header-height: 64px;" in css
    assert "min-height: var(--global-header-height);" in css
    assert "height: var(--global-header-height);" in css
    assert "padding: 0 14px 22px;" in css
    assert "flex: 0 0 auto;" in css
    assert ".brand-copy" in css
    assert "gap: 5px;" in css
    assert ".app-shell.sidebar-collapsed" in css
    assert ".app-shell.sidebar-collapsed .sidebar-toggle" in css
    assert "display: none;" in css
    assert "halpha.dashboard.sidebarCollapsed" in script
    assert "initializeSidebarCollapse()" in script
    assert 'document.querySelector("#brand-logo-toggle")?.addEventListener("click"' in script
    assert "wireTopbarTabDragging()" in script
    assert 'class="tabs topbar-secondary-tabs hidden" id="intel-tabs"' in html
    assert 'class="tabs strategy-operation-tabs topbar-secondary-tabs hidden" id="strategy-operation-tabs"' in html
    assert ".topbar-secondary" in css
    assert ".topbar-secondary-tabs" in css
    assert ".topbar-secondary-tabs .tab-button" in css
    assert "justify-content: flex-start;" in css
    assert "align-items: center;" in css
    assert "scrollbar-width: none;" in css
    assert ".topbar-secondary::-webkit-scrollbar" in css
    assert "can-scroll-right" in css
    assert "mask-image" in css
    assert (
        css.index('body[data-theme="solar"] .strategy-operation-tabs.topbar-secondary-tabs')
        > css.index('body[data-theme="solar"] .strategy-operation-tabs {')
    )


def test_dashboard_startup_event_selectors_exist_in_shell(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)
    ids = set(re.findall(r'id="([^"]+)"', html))
    startup_selectors = set(
        re.findall(r'document\.querySelector\("#([A-Za-z0-9_-]+)"\)\.addEventListener', script)
    )

    assert startup_selectors
    assert startup_selectors <= ids


def test_dashboard_shell_does_not_emit_nul_or_invalid_control_characters(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)

    assert "\x00" not in html
    assert not [char for char in html if ord(char) < 32 and char not in {"\n", "\r", "\t"}]


def test_dashboard_report_preview_and_job_contracts_are_present(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert 'data-report-job="generate"' in html
    assert 'id="topbar-report-generate"' in html
    assert 'id="download-report-button"' not in html
    assert 'id="report-details-drawer-backdrop"' in html
    assert 'id="report-details-drawer-close"' in html
    assert 'id="report-source-files"' in html
    assert 'data-job-intent="run_no_codex"' not in html
    assert 'id="overview-report-job-status"' in html
    assert 'id="reports-report-job-status"' in html
    assert ".report-source-chip" in css
    assert ".report-source-files" in css
    assert ".report-source-row.active" in css
    assert ".report-progress" in css
    assert ".report-milestone-list" in css
    assert ".report-log-stream" in css
    assert ".artifact-document" in css
    assert ".artifact-field-grid" in css
    assert ".report-library-list" in css
    assert ".group-title" not in css
    assert "reportArtifactFiles" in dashboard_reports_script()
    assert "reportArtifactGroups" in dashboard_reports_script()
    assert "renderReportSourceFiles" in script
    assert "renderReportProgress" in script
    assert "reportMilestones" in script
    assert "reportJobRecord" in script
    assert "Generating Report" in script
    assert "selectReportArtifact" in script
    assert "renderReportArtifactPreview" in script
    assert "renderJsonArtifact" in script
    assert "renderCsvArtifact" in script
    assert "renderTextArtifact" in script
    assert "larger than the bounded preview" in script
    assert "data-report-artifact-ref" in script
    assert "wireReportOutline" in script
    assert "annotateReportHeadings" in script
    assert "openReportDetailsDrawer" in script
    assert "closeReportDetailsDrawer" in script
    assert ".hidden" in css
    assert "display: none !important;" in css
    assert "Report artifact recorded" not in script


def test_dashboard_live_workflow_contracts_are_present(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)

    assert 'data-live-endpoint="/api/live"' in html
    assert 'data-live-cycles-endpoint="/api/live/cycles"' in html
    assert 'data-live-alerts-endpoint="/api/live/alerts"' in html
    assert 'data-live-history-endpoint="/api/live/history"' in html
    assert 'id="live-mode-tabs"' in html
    assert 'data-live-mode="now"' in html
    assert 'data-live-mode="reports"' in html
    assert 'data-live-mode="history"' in html
    assert 'id="live-summary"' in html
    assert 'id="live-source-matrix"' in html
    assert 'id="live-filter-data-type"' in html
    assert 'id="live-filter-status"' in html
    assert 'id="live-filter-active"' in html
    assert 'id="live-filter-attention"' in html
    assert 'id="live-intelligence-strip"' in html
    assert 'id="live-intelligence-stream"' in html
    assert 'id="live-report-history"' in html
    assert 'id="live-target-detail"' in html
    assert 'id="live-job-lane"' in html
    assert 'id="live-operations-timeline"' in html
    assert 'id="live-triggered-reports"' in html
    assert 'id="live-alert-archive"' in html
    assert 'id="live-history-filter-start"' in html
    assert 'id="live-history-filter-end"' in html
    assert 'id="live-history-filter-data-type"' in html
    assert 'id="live-history-filter-trigger"' in html
    assert 'id="live-history-filter-kind"' in html
    assert 'id="live-history-filter-status"' in html
    assert 'id="live-history-filter-report-linked"' in html
    assert 'id="live-history-filter-attention"' in html
    assert 'id="live-event-drawer"' in html
    assert "window.HalphaDashboardLive" in dashboard_script()
    css = _style_block(html)
    assert ".live-filter-bar" in css
    assert ".live-history-filter-bar" in css
    assert ".live-mode-tabs" in css
    assert ".live-review-row" in css
    assert ".live-alert-row" in css
    assert ".live-history-event-button" in css
    assert ".live-intelligence-strip" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));" in css
    assert ".live-stream-panel .live-section-head" in css
    assert ".live-intel-card .live-stream-title strong" in css
    assert "hyphens: none;" in css
    assert ".live-target-table" in css
    assert ".live-target-row.active" in css
    assert ".live-job-lane" in css
    assert ".live-job-row" in css
    assert ".live-target-detail" in css
    assert "overflow-wrap: anywhere;" in css
    assert ".live-job-head" in css
    assert "DATA_TYPE_ORDER = [\"ohlcv\", \"text_event\", \"macro_calendar\", \"onchain_flow\", \"derivatives_market\", \"market_anomaly\"]" in dashboard_script()
    assert "renderLiveIntelligenceStrip" in dashboard_script()
    assert "renderLiveJobLane" in dashboard_script()
    assert "renderLiveTriggeredReports" in dashboard_script()
    assert "renderLiveAlertArchive" in dashboard_script()
    assert "renderLiveHistoryFilters" in dashboard_script()
    assert "openLiveEventDrawer" in dashboard_script()
    assert "closeLiveEventDrawer" in dashboard_script()
    assert "filteredLiveHistoryEvents" in dashboard_script()
    assert "data-live-target-key" in dashboard_script()
    assert "data-live-event-id" in dashboard_script()
    assert "matchesLiveFilters" in dashboard_script()
    assert "collectionStatus" in dashboard_script()
    assert "data-monitor-job" not in html
    assert 'data-service-role="monitor"' not in html
    assert 'data-service-action="restart"' not in html
    assert "stop-monitor-button" not in html


def test_dashboard_strategy_chart_shell_contracts_are_present(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert ".kline-panel" in css
    assert ".chart-wrap" in css
    assert ".chart-tooltip" in css
    assert ".chart-tooltip-op-detail" in css
    assert ".pnl-positive" in css
    assert ".pnl-negative" in css
    assert ".candle-hit" in css
    assert ".candle-crosshair" in css
    assert ".strategy-eval-grid" in css
    assert ".strategy-eval-panel" in css
    assert ".strategy-equity-chart" in css
    assert ".strategy-drawdown-chart" in css
    assert ".equity-chart-hit" in css
    assert ".equity-chart-crosshair" in css
    assert ".equity-axis-label" in css
    assert ".drawdown-chart-hit" in css
    assert ".drawdown-chart-crosshair" in css
    assert ".drawdown-axis-label" in css
    assert ".drawdown-boundary-label" in css
    assert ".drawdown-worst-marker" in css
    assert ".strategy-walkforward-card" in css
    assert 'id="backtest-chart"' in html
    assert "OHLCV candlestick chart" in html
    assert "OHLCV only" in script
    assert 'data-strategy-operation-tab="backtest"' in html
    assert 'data-strategy-operation-tab="experiment"' in html
    assert 'data-strategy-operation-tab="optimize"' in html
    assert 'data-strategy-operation-tab="collect"' not in html
    assert 'data-strategy-operation-tab="export"' not in html
    assert "As of help" not in html
    assert "Optional ISO timestamp for no-lookahead reads" not in html
    assert 'id="strategy-profile"' in html
    assert 'id="strategy-profile-overview"' in html
    assert 'id="strategy-backtest-dialog"' in html
    assert 'id="strategy-backtest-detail"' in html
    assert 'id="strategy-backtest-back"' in html
    assert 'id="strategy-metrics"' not in html
    assert ".strategy-backtest-board" in css
    assert ".strategy-backtest-focus" in css
    assert ".strategy-detail-view" in css
    assert ".strategy-profile-card" in css
    assert ".strategy-candidate-card" in css
    assert ".strategy-run-list" in css
    assert ".strategy-run-row" in css
    assert ".strategy-run-sparkline" in css
    assert "renderBacktestRunRow" in script
    assert "backtestRunDuration" in script
    assert "renderBacktestSparkline" in script
    assert "backtestSparklineReturns" in script
    assert "equity_sparkline" in script
    assert "splitSparklineSegments" in script
    assert "strategyBacktestFocusCells" in script
    assert ".strategy-profile-summary" in css
    assert ".operation-progress" in css
    assert ".collect-timeline-track" in css
    assert ".date-range-field" in css
    assert ".range-picker-trigger" in css
    assert ".range-picker-popover" in css
    assert ".range-picker-hint" not in css
    assert "body[data-theme=\"solar\"] .range-picker-presets," not in css
    assert "body[data-theme=\"solar\"] .range-picker-actions," not in css
    assert ".range-picker-day.range-start" in css
    assert ".range-picker-day.in-range" in css
    assert "renderStrategyOhlcvPreview" in script
    assert "loadStrategyChartPreview" in script
    assert "runStrategyCollectPlan" not in script
    assert "loadStrategyCollectPreview" not in script
    assert "candlestick_data_viewer" in script
    assert "candle-hit" in script
    assert "candle-crosshair" in script
    assert "chart-tooltip" in script
    assert "markerDetailRows" in script
    assert "markerTone" in script
    assert "markerColor" in script
    assert "pnlColors" in script
    assert "pnlValueHtml" in script
    assert "isDisplayableBacktestOutput" in script
    assert "renderBacktestDetail" in script
    assert "Unknown symbol" not in script
    assert "#strategy-metrics" not in script
    assert "#0ECB81" not in script
    assert "#F6465D" not in script
    assert "Operations" in script
    assert "Stored operations" not in script
    assert "This table lists stored operation markers for the full evaluation." not in script
    assert "Operation markers" not in html
    assert 'data-strategy-tab="list"' not in html
    assert "renderStrategyTradesPanel" not in script
    assert "strategyMarkerTable" not in script
    assert "strategyOperationScopeNotice" not in script
    assert ".strategy-marker-table" not in css
    assert "Trade operations" in html
    assert "Recent operations" not in html
    assert "backtestRunMeta" in script
    assert "No backtest runs recorded." in script
    assert "Cost and Funding" in script
    assert "Walk-forward" in script
    assert "renderStrategyEvaluationPanels" in script
    assert "renderEquityCurveSvg" in script
    assert "resetEquityCurveView" in script
    assert "renderDrawdownCurveSvg" in script
    assert "resetDrawdownCurveView" in script
    assert "EQUITY_CHART_MAX_POINTS" in script
    assert "aggregateEquityPoints" in script
    assert "aggregateDrawdownPoints" in script
    assert "drawdownPointsFromEquityCurve" in script
    assert "lastDeltaPoints" in script
    assert 'id="strategy-equity-chart"' in script
    assert 'id="strategy-drawdown-chart"' in script
    assert 'metricCell("Start equity"' not in script
    assert 'metricCell("Latest equity"' not in script
    assert 'metricCell("Worst drawdown"' not in script
    assert "derived from bounded equity" not in script
    assert "renderStrategyDrawdownPanel" in script
    assert "onwheel" in script
    assert "onpointerdown" in script
    assert "onpointermove" in script
    assert "drag.lastDeltaBars" in script
    assert "requestAnimationFrame" in script
    assert "downloadSelectedOhlcv" not in html
    assert "sampleVisualization" not in script
    assert "sampleIntelItems" not in script
    assert 'id="strategy-evaluation-window"' in html
    assert 'aria-label="Backtest window help" data-tooltip=' not in html
    assert 'aria-label="Backtest window help" title=' not in html
    assert ".app-tooltip" in css
    assert "body[data-theme=\"solar\"] .app-tooltip" in css
    assert "initializeTooltips" in script
    assert "migrateNativeTooltips" in script
    assert "MutationObserver" in script
    assert "removeAttribute(\"title\")" in script
    assert "chart-tools" not in html
    assert "tool-dot" not in html
    assert "chart-window-control" in html
    assert "segmented-button" in html
    chart_controls = html[html.index('id="strategy-chart-range"') : html.index('id="backtest-chart"')]
    assert 'value="all"' not in chart_controls
    assert 'data-strategy-window="all"' not in chart_controls
    assert "Show latest 30 candles" in chart_controls
    assert "Show latest 360 candles" in chart_controls
    assert 'data-strategy-window="30"' in chart_controls
    assert 'data-strategy-window="360"' in chart_controls
    assert 'strategyWindow: "30"' in script
    assert '["30", "90", "180", "360"]' in script
    assert "lookback: Number(windowValue)" in script
    assert "BACKTEST_CHART_MAX_CANDLES" in script
    assert "backtestSampleWindow" in script
    assert "limit: request.limit || request.lookback" in script
    assert "height: 52vh" not in css
    assert "align-self: start;" in css
    assert ".strategy-operation-tree-panel" in css
    assert "height: calc(clamp(360px, calc(100vh - 330px), 470px) + 111px);" in css
    assert "function visibleBacktestVisualization(item)" in script
    assert "function fullBacktestVisualization(item)" in script
    assert "return applyStrategyWindow(strategyVisualization(item), state.strategyWindow, state.strategyFocusedMarkerTime);" in script
    assert "focusStrategyMarker" in script
    assert "data-strategy-marker-time" in script
    assert "strategy-marker-jump" not in script


def test_strategy_chart_moving_average_uses_full_series_when_panning(tmp_path: Path) -> None:
    node = shutil.which("node") or shutil.which("node.exe")
    if node is None:
        pytest.skip("node is required for the strategy chart moving-average regression test.")
    chart_path = tmp_path / "dashboard_strategy_chart.js"
    chart_path.write_text(dashboard_strategy_chart_script(), encoding="utf-8")
    spec_path = tmp_path / "strategy_chart_ma_regression.js"
    spec_path.write_text(_STRATEGY_CHART_MA_REGRESSION, encoding="utf-8")

    result = subprocess.run(
        [node, str(spec_path)],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
        env={**os.environ, "HALPHA_CHART_SCRIPT": str(chart_path)},
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_strategy_equity_chart_has_axes_hover_and_bounded_sampling(tmp_path: Path) -> None:
    node = shutil.which("node") or shutil.which("node.exe")
    if node is None:
        pytest.skip("node is required for the strategy equity chart regression test.")
    chart_path = tmp_path / "dashboard_strategy_chart.js"
    chart_path.write_text(dashboard_strategy_chart_script(), encoding="utf-8")
    spec_path = tmp_path / "strategy_equity_chart_regression.js"
    spec_path.write_text(_STRATEGY_EQUITY_CHART_REGRESSION, encoding="utf-8")

    result = subprocess.run(
        [node, str(spec_path)],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
        env={**os.environ, "HALPHA_CHART_SCRIPT": str(chart_path)},
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_strategy_drawdown_chart_has_axes_worst_marker_and_navigation(tmp_path: Path) -> None:
    node = shutil.which("node") or shutil.which("node.exe")
    if node is None:
        pytest.skip("node is required for the strategy drawdown chart regression test.")
    chart_path = tmp_path / "dashboard_strategy_chart.js"
    chart_path.write_text(dashboard_strategy_chart_script(), encoding="utf-8")
    spec_path = tmp_path / "strategy_drawdown_chart_regression.js"
    spec_path.write_text(_STRATEGY_DRAWDOWN_CHART_REGRESSION, encoding="utf-8")

    result = subprocess.run(
        [node, str(spec_path)],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
        env={**os.environ, "HALPHA_CHART_SCRIPT": str(chart_path)},
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_dashboard_intelligence_preview_shell_contracts_are_present(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert ".intelligence-preview" in css
    assert "overflow: visible;" in css
    assert ".intel-preview-sidebar" in css
    assert ".intel-view-filter-controls" in css
    assert ".filter-panel-title" in css
    assert ".intel-filter-search-field" in css
    assert ".filter-actions" in css
    assert ".macro-calendar-mode .intel-view-filter-controls" in css
    assert ".onchain-flow-mode .intel-view-filter-controls" in css
    assert ".derivatives-market-mode .intel-view-filter-controls" in css
    assert ".market-anomaly-mode .intel-view-filter-controls" in css
    assert ".onchain-flow-preview" in css
    assert ".onchain-subtabs" in css
    assert ".onchain-chart-card" in css
    assert ".onchain-chart-scroll" in css
    assert ".onchain-chart-svg" in css
    assert ".onchain-chart-point:hover .onchain-chart-hover-layer" in css
    assert ".onchain-chart-hover-line.horizontal" in css
    assert ".onchain-chart-axis-label" in css
    assert "pointer-events: all;" in css
    assert "mask-image: linear-gradient(90deg" in css
    assert ".onchain-selected-card" in css
    assert ".derivatives-market-preview" in css
    assert ".derivatives-board-card" in css
    assert ".derivatives-context-strip" in css
    assert ".derivatives-pressure-panel" in css
    assert ".market-anomaly-preview" in css
    assert ".anomaly-radar-header" in css
    assert ".anomaly-heatmap" in css
    assert ".anomaly-leaderboard" in css
    assert ".anomaly-detail-card" in css
    assert ".macro-calendar-preview" in css
    assert ".macro-calendar-main" in css
    assert ".macro-month-grid" in css
    assert "height: clamp(680px, calc(100vh - 180px), 980px);" in css
    assert "grid-auto-rows: minmax(112px, 1fr);" in css
    assert ".macro-year-grid" in css
    assert ".macro-event-dialog" in css
    assert ".intel-collect-dialog-controls" in css
    assert ".intelligence-collect-dialog" in css
    assert ".dialog-title-row" in css
    assert ".intel-date-picker" in css
    assert ".intel-calendar-day.has-data" in css
    assert ".intel-date-heading" in css
    assert ".intel-metric-grid" in css
    assert ".macro-event-banner.future" in css
    assert ".macro-event-banner.past" in css
    assert ".intel-preview-row.macro-event-future" in css
    assert ".intel-preview-row.macro-event-past" in css
    assert ".intel-preview-main-head" in css
    assert "border-left: 4px solid var(--primary);" in css
    assert "background: #fff4c2;" in css
    assert ".data-viewer-header-actions" in css
    assert ".intel-properties-trigger" in css
    assert ".drawer-backdrop" in css
    assert ".artifact-drawer" in css
    assert "border-radius: 18px 0 0 18px;" not in css
    assert "border-radius: 0;" in css
    assert ".drawer-header" in css
    assert ".drawer-body" in css
    assert "@keyframes drawer-in" in css
    assert "@keyframes overlay-in" in css
    assert ".intel-timeline-segment.unknown" in css
    assert ".timeline-legend-dot.unknown" in css
    assert ".collect-timeline-segment.unknown" in css
    assert ".data-viewer-issues" in css
    assert ".data-viewer-issue-popover" in css
    assert ".data-viewer-issue-list" in css
    assert "min-width: 118px;" not in css
    assert "compact-button data-viewer-issue-button" in script
    assert "background: #94a3b8;" in css
    assert "Jump date" in script
    assert "Scroll for more records" in script
    assert "Bounded preview limit reached" in script
    assert "Key metrics" in script
    assert "Record context" in script
    assert "macroCalendarTemporalState" in script
    assert "Future event" in script
    assert "Past event" in script
    assert "macroEventTooltip" in script
    assert 'title="${escapeHtml(tooltip)}"' in script
    assert 'aria-label="${escapeHtml(tooltip)}"' in script
    assert "renderMacroCalendarPreview" in script
    assert "renderOnchainFlowPreview" in script
    assert "renderDerivativesMarketPreview" in script
    assert "renderMarketAnomalyPreview" in script
    assert "onchainMetricSeries" in script
    assert "chartPointTooltipLines" in script
    assert "renderChartPointHoverLayer" in script
    assert "data-onchain-class" in script
    assert "data-onchain-metric" in script
    assert "data-onchain-point-index" in script
    assert "data-onchain-jump" in script
    assert "data-derivatives-class" in script
    assert "data-derivatives-metric" in script
    assert "data-anomaly-severity" in script
    assert "data-anomaly-index" in script
    assert "wireOnchainChartDragScroll" in script
    assert "wireOnchainScrollableTabs" in script
    assert "wireHorizontalDragScroll" in script
    assert "suppressClickAfterDrag" in script
    assert "data-macro-calendar-view" in script
    assert "data-macro-list-index" in script
    assert "data-macro-event-index" in script
    assert "data-macro-year-date" in script
    assert "macroCalendarView" in script
    assert "updateIntelligencePropertiesSelection" in script
    assert "openIntelligencePropertiesDrawer" in script
    assert "closeIntelligencePropertiesDrawer" in script
    assert "renderIntelligencePropertiesDrawer" in script
    assert 'id="intel-properties-button"' in script
    assert "data-data-viewer-job-log-toggle" in script
    assert "storeFields.records ?? storeFields.record_count ?? coverage.record_count" not in script
    assert "data-data-viewer-issues" in script
    assert "toggleIssuePopover" in script
    assert 'metricCell("Records"' not in script
    assert 'metricCell("Coverage states"' not in script
    assert 'metricCell("Issues"' not in script
    assert "execution: internal core service" in script
    assert "data-intel-jump-date" in script
    assert "data-strategy-window" in html
    assert ">USDT</span>" not in html
    assert "Latest available window" not in html


def test_dashboard_shell_has_no_unwired_dashboard_controls_or_fabricated_sources(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)

    assert 'id="report-reader-search"' in html
    assert 'id="report-details"' not in html
    assert 'id="report-sources"' not in html
    assert "downloadSelectedReport" not in script
    assert "Report content is not available yet" not in script
    assert 'category === "run_metadata") return "Run manifest";' in script
    assert '"Report artifact"' not in script
    assert '["BTC", "ETH", "USDT", "SOL", "XRP", "ADA"]' not in script
    assert "{max_cycles: 72, interval_seconds: 360}" not in script
    assert "monitor_loop" not in html
    assert "monitor_loop" not in script


_STRATEGY_CHART_MA_REGRESSION = textwrap.dedent(
    r"""
    const fs = require("fs");
    const vm = require("vm");

    const chartScriptPath = process.env.HALPHA_CHART_SCRIPT;
    if (!chartScriptPath) throw new Error("HALPHA_CHART_SCRIPT is required");
    const chartScript = fs.readFileSync(chartScriptPath, "utf8");

    const classList = () => ({
      add() {},
      remove() {},
      toggle() {},
    });
    const parent = {
      querySelector() { return null; },
      appendChild() {},
      getBoundingClientRect() { return {left: 0, top: 0, width: 980, height: 470}; },
    };
    const svg = {
      innerHTML: "",
      parentElement: parent,
      classList: classList(),
      getBoundingClientRect() { return {left: 0, top: 0, width: 980, height: 470}; },
      querySelector() { return {setAttribute() {}}; },
      querySelectorAll(selector) {
        if (selector !== ".candle-hit") return [];
        return [...this.innerHTML.matchAll(/<rect class="candle-hit"[^>]*>/g)].map((match) => {
          const dataset = {};
          for (const [, key, value] of match[0].matchAll(/data-([a-z-]+)="([^"]*)"/g)) {
            dataset[key.replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = value;
          }
          return {dataset, addEventListener() {}};
        });
      },
      addEventListener() {},
      setPointerCapture() {},
    };
    const context = {
      window: {
        HalphaDashboardShared: {
          escapeHtml(value) {
            return String(value ?? "")
              .replaceAll("&", "&amp;")
              .replaceAll('"', "&quot;")
              .replaceAll("<", "&lt;")
              .replaceAll(">", "&gt;");
          },
          formatNumber(value) { return String(value); },
          pnlColors() { return {up: "#0a8", down: "#d33", neutral: "#777"}; },
          formatTimestamp(value) { return String(value || ""); },
        },
      },
      document: {
        querySelector(selector) { return selector === "#chart" ? svg : null; },
        createElement() {
          return {
            className: "",
            classList: classList(),
            style: {},
            innerHTML: "",
            offsetWidth: 230,
            offsetHeight: 160,
          };
        },
      },
      requestAnimationFrame(callback) {
        callback();
        return 1;
      },
      cancelAnimationFrame() {},
      console,
    };
    context.globalThis = context;
    vm.createContext(context);
    vm.runInContext(chartScript, context, {filename: "dashboard_strategy_chart.js"});

    const bars = Array.from({length: 50}, (_, index) => ({
      time: `t${index}`,
      open: index,
      high: 100,
      low: 0,
      close: index,
      volume: 1,
    }));
    const chart = context.window.HalphaDashboardStrategyChart;

    function movingAverageY(time, color) {
      const html = svg.innerHTML;
      const times = [...html.matchAll(/data-candle-time="([^"]+)"/g)].map((match) => match[1]);
      const line = [...html.matchAll(/<polyline points="([^"]+)"[^>]*stroke="([^"]+)"/g)]
        .find((match) => match[2] === color);
      if (!line) throw new Error(`moving-average line ${color} was not rendered`);
      const index = times.indexOf(time);
      if (index < 0) throw new Error(`${time} is not visible in ${times.join(",")}`);
      const point = line[1].trim().split(/\s+/)[index];
      return Number(point.split(",")[1]);
    }

    chart.renderCandlestickSvg("#chart", {symbol: "BTCUSDT", timeframe: "4h", bars}, {});
    svg.onwheel({preventDefault() {}, clientX: 490, deltaY: -1});
    const ma12Before = movingAverageY("t10", "#4f8cff");
    const ma34Before = movingAverageY("t10", "#f59e0b");
    svg.onpointerdown({button: 0, clientX: 500, pointerId: 1});
    svg.onpointerup({clientX: 420, pointerId: 1});
    const ma12After = movingAverageY("t10", "#4f8cff");
    const ma34After = movingAverageY("t10", "#f59e0b");

    const ma12Delta = Math.abs(ma12Before - ma12After);
    const ma34Delta = Math.abs(ma34Before - ma34After);
    console.log(JSON.stringify({ma12Before, ma12After, ma12Delta, ma34Before, ma34After, ma34Delta}));
    if (ma12Delta > 1e-9 || ma34Delta > 1e-9) {
      throw new Error(`moving averages changed after pan: MA12 delta=${ma12Delta}, MA34 delta=${ma34Delta}`);
    }
    """
)


_STRATEGY_EQUITY_CHART_REGRESSION = textwrap.dedent(
    r"""
    const fs = require("fs");
    const vm = require("vm");

    const chartScriptPath = process.env.HALPHA_CHART_SCRIPT;
    if (!chartScriptPath) throw new Error("HALPHA_CHART_SCRIPT is required");
    const chartScript = fs.readFileSync(chartScriptPath, "utf8");

    const classList = () => ({
      add() {},
      remove() {},
      toggle() {},
    });
    const parent = {
      tooltip: null,
      querySelector(selector) {
        return selector === ".chart-tooltip" ? this.tooltip : null;
      },
      appendChild(node) {
        this.tooltip = node;
      },
      getBoundingClientRect() { return {left: 0, top: 0, width: 900, height: 260}; },
    };
    const svg = {
      innerHTML: "",
      parentElement: parent,
      classList: classList(),
      lastHits: [],
      crosshairAttrs: {},
      getBoundingClientRect() { return {left: 0, top: 0, width: 900, height: 260}; },
      querySelector(selector) {
        if (selector === ".equity-chart-crosshair") {
          return {
            setAttribute: (name, value) => {
              this.crosshairAttrs[name] = value;
            },
          };
        }
        return {setAttribute() {}};
      },
      querySelectorAll(selector) {
        if (selector !== ".equity-chart-hit") return [];
        this.lastHits = [...this.innerHTML.matchAll(/<circle class="equity-chart-hit"[^>]*>/g)].map((match) => {
          const dataset = {};
          const listeners = {};
          for (const [, key, value] of match[0].matchAll(/data-([a-z-]+)="([^"]*)"/g)) {
            dataset[key.replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = value;
          }
          return {
            dataset,
            listeners,
            addEventListener(name, callback) { listeners[name] = callback; },
          };
        });
        return this.lastHits;
      },
      addEventListener() {},
      setPointerCapture() {},
    };
    const context = {
      window: {
        HalphaDashboardShared: {
          escapeHtml(value) {
            return String(value ?? "")
              .replaceAll("&", "&amp;")
              .replaceAll('"', "&quot;")
              .replaceAll("<", "&lt;")
              .replaceAll(">", "&gt;");
          },
          formatNumber(value) { return String(value); },
          pnlColors() { return {profit: "#087f5b", loss: "#c92a2a", up: "#087f5b", down: "#c92a2a"}; },
          formatTimestamp(value) { return String(value || ""); },
        },
      },
      document: {
        querySelector(selector) { return selector === "#equity" ? svg : null; },
        createElement() {
          return {
            className: "",
            classList: classList(),
            style: {},
            innerHTML: "",
            offsetWidth: 230,
            offsetHeight: 160,
          };
        },
      },
      requestAnimationFrame(callback) {
        callback();
        return 1;
      },
      cancelAnimationFrame() {},
      console,
    };
    context.globalThis = context;
    vm.createContext(context);
    vm.runInContext(chartScript, context, {filename: "dashboard_strategy_chart.js"});

    const chart = context.window.HalphaDashboardStrategyChart;
    const curve = Array.from({length: 400}, (_, index) => ({
      time: `2026-01-${String((index % 28) + 1).padStart(2, "0")}T00:00:00Z`,
      equity: 1 + Math.sin(index / 11) * 0.04 + (index - 200) / 10000,
    }));
    chart.renderEquityCurveSvg("#equity", curve, {displayTimezone: "UTC"});
    const hitCount = (svg.innerHTML.match(/class="equity-chart-hit"/g) || []).length;
    if (hitCount > chart.EQUITY_CHART_MAX_POINTS) {
      throw new Error(`expected bounded hit nodes, got ${hitCount}`);
    }
    for (const required of [
      "equity-axis-label y",
      "equity-axis-label x",
      "equity-baseline",
      "equity-chart-crosshair",
      "equity-chart-segment profit",
      "equity-chart-segment loss",
    ]) {
      if (!svg.innerHTML.includes(required)) {
        throw new Error(`missing ${required}`);
      }
    }
    if (!svg.lastHits.length || !svg.lastHits[0].listeners.mousemove) {
      throw new Error("equity hover hit listeners were not wired");
    }
    svg.lastHits[0].listeners.mousemove({clientX: 120, clientY: 80});
    if (!parent.tooltip?.innerHTML.includes("Equity") || !parent.tooltip?.innerHTML.includes("Change")) {
      throw new Error("equity tooltip did not render point details");
    }
    if (svg.crosshairAttrs.visibility !== "visible") {
      throw new Error("equity crosshair did not become visible on hover");
    }
    svg.onwheel({preventDefault() {}, clientX: 450, deltaY: -1});
    if (!svg.innerHTML.includes("/ 400 points")) {
      throw new Error("equity wheel zoom did not create a bounded viewport label");
    }
    const zoomedHitCount = (svg.innerHTML.match(/class="equity-chart-hit"/g) || []).length;
    if (zoomedHitCount > chart.EQUITY_CHART_MAX_POINTS) {
      throw new Error(`expected bounded zoomed hit nodes, got ${zoomedHitCount}`);
    }
    const sampled = chart.aggregateEquityPoints([
      {index: 0, value: 1},
      {index: 1, value: 1.08},
      {index: 2, value: 0.75},
      {index: 3, value: 1.03},
      {index: 4, value: 1.45},
    ], 2);
    if (sampled.length !== 2 || sampled[0].index !== 1 || sampled[1].index !== 4) {
      throw new Error(`unexpected absolute-extreme sampling: ${JSON.stringify(sampled)}`);
    }
    console.log(JSON.stringify({hitCount, zoomedHitCount}));
    """
)


_STRATEGY_DRAWDOWN_CHART_REGRESSION = textwrap.dedent(
    r"""
    const fs = require("fs");
    const vm = require("vm");

    const chartScriptPath = process.env.HALPHA_CHART_SCRIPT;
    if (!chartScriptPath) throw new Error("HALPHA_CHART_SCRIPT is required");
    const chartScript = fs.readFileSync(chartScriptPath, "utf8");

    const classList = () => ({
      add() {},
      remove() {},
      toggle() {},
    });
    const parent = {
      tooltip: null,
      querySelector(selector) {
        return selector === ".chart-tooltip" ? this.tooltip : null;
      },
      appendChild(node) {
        this.tooltip = node;
      },
      getBoundingClientRect() { return {left: 0, top: 0, width: 900, height: 260}; },
    };
    const svg = {
      innerHTML: "",
      parentElement: parent,
      classList: classList(),
      lastHits: [],
      crosshairAttrs: {},
      getBoundingClientRect() { return {left: 0, top: 0, width: 900, height: 260}; },
      querySelector(selector) {
        if (selector === ".drawdown-chart-crosshair") {
          return {
            setAttribute: (name, value) => {
              this.crosshairAttrs[name] = value;
            },
          };
        }
        return {setAttribute() {}};
      },
      querySelectorAll(selector) {
        if (selector !== ".drawdown-chart-hit, .drawdown-worst-hit" && selector !== ".drawdown-chart-hit") return [];
        const pattern = selector === ".drawdown-chart-hit"
          ? /<circle class="drawdown-chart-hit"[^>]*>/g
          : /<circle class="(?:drawdown-chart-hit|drawdown-worst-hit)"[^>]*>/g;
        this.lastHits = [...this.innerHTML.matchAll(pattern)].map((match) => {
          const dataset = {};
          const listeners = {};
          const className = (match[0].match(/class="([^"]+)"/) || [])[1] || "";
          for (const [, key, value] of match[0].matchAll(/data-([a-z-]+)="([^"]*)"/g)) {
            dataset[key.replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = value;
          }
          return {
            className,
            dataset,
            listeners,
            addEventListener(name, callback) { listeners[name] = callback; },
          };
        });
        return this.lastHits;
      },
      addEventListener() {},
      setPointerCapture() {},
    };
    const context = {
      window: {
        HalphaDashboardShared: {
          escapeHtml(value) {
            return String(value ?? "")
              .replaceAll("&", "&amp;")
              .replaceAll('"', "&quot;")
              .replaceAll("<", "&lt;")
              .replaceAll(">", "&gt;");
          },
          formatNumber(value) { return String(value); },
          pnlColors() { return {profit: "#087f5b", loss: "#c92a2a", up: "#087f5b", down: "#c92a2a"}; },
          formatTimestamp(value) { return String(value || ""); },
        },
      },
      document: {
        querySelector(selector) { return selector === "#drawdown" ? svg : null; },
        createElement() {
          return {
            className: "",
            classList: classList(),
            style: {},
            innerHTML: "",
            offsetWidth: 230,
            offsetHeight: 160,
          };
        },
      },
      requestAnimationFrame(callback) {
        callback();
        return 1;
      },
      cancelAnimationFrame() {},
      console,
    };
    context.globalThis = context;
    vm.createContext(context);
    vm.runInContext(chartScript, context, {filename: "dashboard_strategy_chart.js"});

    const chart = context.window.HalphaDashboardStrategyChart;
    const curve = Array.from({length: 400}, (_, index) => {
      const recovery = index > 240 ? (index - 240) / 260 : 0;
      const shock = index > 120 && index < 240 ? (index - 120) / 35 : 0;
      const equity = 1.2 + index / 2000 - Math.min(0.32, shock * 0.05) + recovery * 0.15;
      return {
        time: `2026-02-${String((index % 28) + 1).padStart(2, "0")}T00:00:00Z`,
        equity,
      };
    });
    chart.renderDrawdownCurveSvg("#drawdown", curve, {displayTimezone: "UTC"});
    const hitCount = (svg.innerHTML.match(/class="drawdown-chart-hit"/g) || []).length;
    if (hitCount > chart.EQUITY_CHART_MAX_POINTS) {
      throw new Error(`expected bounded hit nodes, got ${hitCount}`);
    }
    for (const required of [
      "drawdown-axis-label y",
      "drawdown-axis-label x",
      "drawdown-boundary-label start",
      "drawdown-boundary-label end",
      "drawdown-zero-line",
      "drawdown-chart-line",
      "drawdown-worst-marker",
      "drawdown-worst-hit",
    ]) {
      if (!svg.innerHTML.includes(required)) {
        throw new Error(`missing ${required}`);
      }
    }
    const worstHit = svg.lastHits.find((hit) => hit.className.includes("drawdown-worst-hit"));
    if (!worstHit || !worstHit.listeners.mousemove) {
      throw new Error("drawdown worst marker hover was not wired");
    }
    worstHit.listeners.mousemove({clientX: 420, clientY: 120});
    if (!parent.tooltip?.innerHTML.includes("Max drawdown") || !parent.tooltip?.innerHTML.includes("Drawdown")) {
      throw new Error("drawdown worst tooltip did not render details");
    }
    if (svg.crosshairAttrs.visibility !== "visible") {
      throw new Error("drawdown crosshair did not become visible on hover");
    }
    const before = (svg.innerHTML.match(/<text class="drawdown-chart-status"[^>]*>([^<]+)<\/text>/) || [])[1];
    svg.onwheel({preventDefault() {}, clientX: 450, deltaY: -1});
    const after = (svg.innerHTML.match(/<text class="drawdown-chart-status"[^>]*>([^<]+)<\/text>/) || [])[1];
    if (!after || !after.includes("/ 400 points") || before === after) {
      throw new Error(`drawdown wheel zoom did not update viewport label: ${before} -> ${after}`);
    }
    const zoomedHitCount = (svg.innerHTML.match(/class="drawdown-chart-hit"/g) || []).length;
    if (zoomedHitCount > chart.EQUITY_CHART_MAX_POINTS) {
      throw new Error(`expected bounded zoomed hit nodes, got ${zoomedHitCount}`);
    }
    const sampled = chart.aggregateDrawdownPoints([
      {index: 0, value: 0},
      {index: 1, value: -4},
      {index: 2, value: -1},
      {index: 3, value: -8},
      {index: 4, value: -2},
    ], 2);
    if (sampled.length !== 2 || sampled[0].index !== 1 || sampled[1].index !== 3) {
      throw new Error(`unexpected drawdown sampling: ${JSON.stringify(sampled)}`);
    }
    console.log(JSON.stringify({hitCount, zoomedHitCount, before, after}));
    """
)


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
