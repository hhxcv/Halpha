from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app


EXPECTED_DASHBOARD_VIEWS = {
    "overview",
    "runs",
    "artifacts",
    "data",
    "strategies",
    "monitor",
    "workbench",
    "decision-risk",
    "event-alert",
    "text-intelligence",
    "outcomes",
    "commands",
}


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


def test_dashboard_shell_navigation_matches_view_sections(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    parser = DashboardShellParser()
    parser.feed(html)

    assert parser.meta_viewport == "width=device-width, initial-scale=1"
    assert EXPECTED_DASHBOARD_VIEWS <= parser.nav_targets
    assert EXPECTED_DASHBOARD_VIEWS <= parser.view_sections
    assert parser.nav_targets == parser.view_sections


def test_dashboard_responsive_css_contracts_cover_desktop_and_small_viewports(tmp_path: Path) -> None:
    css = _style_block(_dashboard_html(tmp_path))

    assert ".app-shell" in css
    assert "grid-template-columns: 248px minmax(0, 1fr);" in css
    assert "@media (max-width: 1180px)" in css
    assert ".command-center-layout" in css
    assert ".text-intelligence-layout" in css
    assert "grid-template-columns: 1fr;" in css
    assert "@media (max-width: 760px)" in css
    assert ".sidebar" in css
    assert "position: static;" in css
    assert ".nav" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".preview-body" in css
    assert "overflow: auto;" in css


def test_dashboard_interaction_hooks_cover_primary_workflows(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)
    parser = DashboardShellParser()
    parser.feed(html)

    assert "data-command-intent" in parser.data_attrs
    assert "data-monitor-action" in parser.data_attrs
    assert "data-schedule-action" in parser.data_attrs
    assert "data-preview-endpoint" in parser.data_attrs
    assert 'document.querySelectorAll("[data-view-target]")' in script
    assert "setView(node.dataset.viewTarget)" in script
    assert 'querySelectorAll("[data-artifact-path]")' in script
    assert "loadArtifactPreview(button.dataset.artifactPath" in script
    assert "startCommandJob(button.dataset.commandIntent)" in script
    assert "startMonitorJob(button.dataset.monitorAction)" in script
    assert "runDailyScheduleAction(button.dataset.scheduleAction)" in script
    assert "refreshCurrentView" in script


def test_dashboard_startup_event_selectors_exist_in_shell(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)
    ids = set(re.findall(r'id="([^"]+)"', html))
    startup_selectors = set(
        re.findall(r'document\.querySelector\("#([A-Za-z0-9_-]+)"\)\.addEventListener', script)
    )

    assert startup_selectors
    assert startup_selectors <= ids


def test_dashboard_shell_does_not_emit_nul_control_characters(tmp_path: Path) -> None:
    html = _dashboard_html(tmp_path)
    script = _script_block(html)

    assert "\x00" not in html
    assert "[\\x00-\\x20]" in script


def test_dashboard_preview_job_and_monitor_smoke_contracts_are_present(tmp_path: Path) -> None:
    script = _script_block(_dashboard_html(tmp_path))

    assert "renderArtifactPreview(payload, target, targetSelector, options)" in script
    assert "previewDisplayKind" in script
    assert "renderCsvPreviewTable" in script
    assert "renderPreviewTable" in script
    assert "previewSourceRefs" in script
    assert "commandJobRequest(intent)" in script
    assert "textCommandJobRequest(intent)" in script
    assert "strategyCommandJobRequest(intent)" in script
    assert "positiveInputValue" in script
    assert "renderMonitor(payload)" in script
    assert "renderMonitorAlertCounts" in script
    assert "refreshMonitorJobs" in script


def _dashboard_html(tmp_path: Path) -> str:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))
    response = client.get("/")
    assert response.status_code == 200
    return response.text


def _style_block(html: str) -> str:
    start = html.index("<style>") + len("<style>")
    end = html.index("</style>", start)
    return html[start:end]


def _script_block(html: str) -> str:
    start = html.index("<script>") + len("<script>")
    end = html.index("</script>", start)
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
