from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from dashboard_asset_helpers import (
    dashboard_css,
    dashboard_script,
)


EXPECTED_DASHBOARD_VIEWS = {
    "overview",
    "reports",
    "strategies",
    "monitor",
    "intelligence",
    "settings",
}


REQUIRED_SCRIPT_ASSETS = (
    "/assets/dashboard_shared.js",
    "/assets/dashboard_dialogs.js",
    "/assets/dashboard_reports.js",
    "/assets/dashboard_strategy_chart.js",
    "/assets/dashboard_monitor.js",
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
        ".monitor-layout",
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


def test_dashboard_shell_uses_monitor_status_without_local_mode_badges(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert "System healthy" not in html
    assert "Local mode" not in html
    assert "No data leaves this device through the dashboard UI." not in html
    assert 'id="sidebar-monitor-dot"' in html
    assert 'id="sidebar-monitor-title">Monitor status</span>' in html
    assert 'id="sidebar-monitor-text">Loading monitor status.</div>' in html
    assert "monitorSidebarState" in script
    assert "renderSidebarMonitorStatus" in script
    assert "Monitoring is enabled and running." in script
    assert "loadMonitorPayload().catch(() => renderSidebarMonitorStatus())" in script
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
        "intel-preview-as-of-mode",
        "intel-preview-as-of",
    ],
)
def test_dashboard_exposes_primary_filter_controls(tmp_path: Path, selector_id: str) -> None:
    html = _dashboard_html(tmp_path)

    assert f'id="{selector_id}"' in html


@pytest.mark.parametrize(
    "contract",
    [
        'data-strategy-tab="trades"',
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

    assert 'id="config-profile" class="readonly-value"' in html
    assert contract in html


def test_dashboard_status_class_covers_nonterminal_states(tmp_path: Path) -> None:
    script = _script_block(_dashboard_html(tmp_path))

    assert '"disabled", "not_generated", "not_run"' in script
    assert 'return "skipped";' in script
    assert '"insufficient_data", "unavailable"' in script
    assert 'return "partial";' in script


def test_dashboard_report_job_controls_expose_dom_contracts(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    parser = DashboardShellParser()
    parser.feed(html)

    assert "data-job-intent" in parser.data_attrs
    assert "data-preview-endpoint" in parser.data_attrs
    assert 'data-report-job="generate"' in html
    assert 'id="overview-report-job-status"' in html
    assert 'id="reports-report-job-status"' in html


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
            "strategy-symbol",
            "strategy-timeframe",
            "strategy-name",
            "strategy-evaluation-window",
            "strategy-ohlcv-source-options",
            "strategy-backtest-progress",
            "strategy-experiment-results",
            "strategy-optimize-results",
        "strategy-chart-source",
        "strategy-chart-symbol",
        "strategy-chart-timeframe",
        "strategy-chart-range",
        "strategy-chart-refresh",
        "strategy-collect-source",
        "strategy-collect-symbol",
        "strategy-collect-timeframe",
        "strategy-collect-targets",
        "strategy-collect-range",
        "strategy-collect-date-range",
        "strategy-collect-start",
        "strategy-collect-end",
        "strategy-collect-timeline",
        "strategy-collect-progress",
        "strategy-export-source",
        "strategy-export-symbol",
        "strategy-export-timeframe",
        "strategy-export-range",
        "strategy-export-date-range",
        "strategy-export-start",
        "strategy-export-end",
        "strategy-export-as-of",
        "strategy-export-format",
        "strategy-export-progress",
        "strategy-data-job-panel",
        "intel-overview-panel",
        "intel-overview-kpis",
        "intel-overview-content",
        "intel-data-viewer",
        "intel-data-type",
        "intel-collect-range",
        "intel-collect-date-range",
        "intel-collect-start",
        "intel-collect-end",
        "intel-collect-reset",
        "intel-preview-range",
        "intel-preview-date-range",
        "intel-preview-as-of-mode",
        "intel-preview-as-of-custom-field",
        "intel-preview-start",
        "intel-preview-end",
        "intel-preview-as-of",
        "intel-preview-reset",
        "intel-data-coverage",
        "intel-data-preview-panel",
        "intel-data-job-panel",
    ):
        assert f'id="{selector_id}"' in html
    assert "Identity filter key" not in html
    assert "Identity filter value" not in html
    assert "Source scope" not in html
    assert "Point-in-time view" in html
    assert "Point-in-time help" in html
    assert "Optional no-lookahead cutoff" in html
    assert html.count("data-date-range-picker") == 4
    assert html.count("data-range-picker-label") == 4
    for action in (
        "strategy-timeline",
        "strategy-collect",
        "strategy-export",
        "intel-collect",
    ):
        assert f'data-data-viewer-action="{action}"' in html
    assert 'id="strategy-collect-preview"' not in html
    assert 'id="strategy-collect-plan"' not in html
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
    assert "runStrategyExport" in script
    assert "renderOperationProgress" in script
    assert "renderIntelligenceOverview" in script
    assert "loadIntelligenceDataPanels" in script
    assert "renderIntelligenceTimeline" in script
    assert "renderIntelligencePreview" in script
    assert "renderDateJumpCalendar" in script
    assert "previewListItemsWithDates" in script
    assert "recordMetricFacts" in script
    assert "intelPreviewDisplayLimit" in script
    assert "intel-preview-keyword" in script
    assert "intel-preview-category-filter" in script
    assert "Search loaded records" in script
    assert "recordCategory" in script
    assert "Unclassified" in script
    assert "wireDateRangePickers" in script
    assert "data-range-day" in script
    assert "range-start" in script
    assert "range-end" in script
    assert "in-range" in script
    assert "data-range-quick" in script
    assert "syncDateRangePicker" in script
    assert "Click two dates to set one UTC range." in script
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
    assert "Check the timeline to distinguish no_data from not_collected, partial, failed, stale, or unknown coverage." in script
    assert "Creating bounded export under data/exports." in script


def test_dashboard_monitor_service_controls_expose_dom_contracts(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    parser = DashboardShellParser()
    parser.feed(html)

    assert "data-monitor-job" in parser.data_attrs
    assert "data-service-role" in parser.data_attrs
    assert "data-service-action" in parser.data_attrs
    assert 'data-service-role="monitor"' in html
    assert 'data-service-role="schedule"' not in html
    assert 'data-service-action="restart"' in html
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
    assert "data-setting-path" in script
    assert 'min="0" max="1" step="0.01"' in script
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
    assert ".loading-surface" in css
    assert "renderInitialLoadingPlaceholders()" in script
    assert "renderOverviewLoading()" in script
    assert "renderReportsLoading()" in script
    assert "renderStrategiesLoading()" in script
    assert "renderMonitorLoading()" in script
    assert "renderIntelligenceLoading()" in script
    assert "renderSettingsLoading()" in script
    assert "VIEW_REFRESH_TTL_MS = 15000" in script
    assert "state.viewRefreshPromises[view]" in script
    assert 'refreshCurrentView({force: true})' in script


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


def test_dashboard_shell_does_not_emit_nul_or_invalid_control_characters(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)

    assert "\x00" not in html
    assert not [char for char in html if ord(char) < 32 and char not in {"\n", "\r", "\t"}]


def test_dashboard_report_preview_and_job_contracts_are_present(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert 'data-report-job="generate"' in html
    assert 'data-job-intent="run_no_codex"' not in html
    assert 'id="overview-report-job-status"' in html
    assert 'id="reports-report-job-status"' in html
    assert ".hidden" in css
    assert "display: none !important;" in css
    assert "Report artifact recorded" not in script


def test_dashboard_monitor_workflow_contracts_are_present(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)

    assert "data-monitor-job" in html
    assert 'data-service-role="monitor"' in html
    assert 'data-service-action="restart"' in html
    assert "stop-monitor-button" not in html


def test_dashboard_strategy_chart_shell_contracts_are_present(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert ".kline-panel" in css
    assert ".chart-wrap" in css
    assert ".chart-tooltip" in css
    assert ".chart-tooltip-op-detail" in css
    assert ".candle-hit" in css
    assert ".candle-crosshair" in css
    assert ".strategy-eval-grid" in css
    assert ".strategy-eval-panel" in css
    assert ".strategy-walkforward-card" in css
    assert 'id="backtest-chart"' in html
    assert "OHLCV candlestick chart" in html
    assert "OHLCV only" in script
    assert 'data-strategy-operation-tab="backtest"' in html
    assert 'data-strategy-operation-tab="collect"' in html
    assert 'data-strategy-operation-tab="export"' in html
    assert "As of help" in html
    assert "Optional ISO timestamp for no-lookahead reads" in html
    assert ".operation-progress" in css
    assert ".collect-timeline-track" in css
    assert ".date-range-field" in css
    assert ".range-picker-trigger" in css
    assert ".range-picker-popover" in css
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
    assert "Operations" in script
    assert "Visible operations" in script
    assert "Full per-trade rows are not stored in this artifact." in script
    assert "Operation markers" in html
    assert "Recent operations" in html
    assert "backtestRunMeta" in script
    assert "No backtest runs recorded." in script
    assert "Cost and Funding" in script
    assert "Walk-forward" in script
    assert "renderStrategyEvaluationPanels" in script
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
    assert "chart-tools" in html
    assert "tool-dot" in html
    chart_controls = html[html.index('id="strategy-chart-range"') : html.index('id="backtest-chart"')]
    assert 'value="all"' not in chart_controls
    assert 'data-strategy-window="all"' not in chart_controls
    assert "Latest 30 candles" in chart_controls
    assert "Latest 360 candles" in chart_controls
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
    assert "max-height: calc(clamp(360px, calc(100vh - 330px), 470px) + 122px);" in css
    assert "function visibleBacktestVisualization(item)" in script
    assert "return backtestVisualization(item);" in script


def test_dashboard_intelligence_preview_shell_contracts_are_present(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    css = _style_block(html)
    script = _script_block(html)

    assert ".intelligence-preview" in css
    assert "overflow: visible;" in css
    assert ".intel-preview-sidebar" in css
    assert ".intel-list-filterbar" in css
    assert ".intel-filter-actions" in css
    assert ".intel-date-picker" in css
    assert ".intel-calendar-day.has-data" in css
    assert ".intel-date-heading" in css
    assert ".intel-metric-grid" in css
    assert ".macro-event-banner.future" in css
    assert ".macro-event-banner.past" in css
    assert ".intel-preview-row.macro-event-future" in css
    assert ".intel-preview-row.macro-event-past" in css
    assert ".intel-timeline-segment.unknown" in css
    assert ".timeline-legend-dot.unknown" in css
    assert ".collect-timeline-segment.unknown" in css
    assert ".data-viewer-issues" in css
    assert ".data-viewer-issue-popover" in css
    assert ".data-viewer-issue-list" in css
    assert "background: #94a3b8;" in css
    assert "Jump date" in script
    assert "Scroll for more records" in script
    assert "Bounded preview limit reached" in script
    assert "Key metrics" in script
    assert "Record context" in script
    assert "macroCalendarTemporalState" in script
    assert "Future event" in script
    assert "Past event" in script
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
    assert "Report content is not available yet" not in script
    assert '"Run manifest"' not in script
    assert '"Report artifact"' not in script
    assert '["BTC", "ETH", "USDT", "SOL", "XRP", "ADA"]' not in script
    assert "{max_cycles: 72, interval_seconds: 360}" not in script
    assert "monitor_loop" not in html
    assert "monitor_loop" not in script


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
