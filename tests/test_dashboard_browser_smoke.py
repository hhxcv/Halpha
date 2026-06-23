from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import textwrap
import threading
import time
from urllib.request import urlopen

from fastapi.testclient import TestClient
import pytest
import uvicorn

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from dashboard_asset_helpers import dashboard_script


BROWSER_SMOKE_ENABLED = os.environ.get("HALPHA_BROWSER_SMOKE") == "1"


def test_dashboard_browser_smoke_static_navigation_contract(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    app = create_dashboard_app(config, config_path=config_path)

    response = TestClient(app).get("/")
    assert response.status_code == 200
    html = response.text
    script = dashboard_script()
    for view in _PRIMARY_VIEWS:
        assert f'data-view-target="{view}"' in html
        assert f'id="{view}-view"' in html
        assert f'"{view}"' in _PLAYWRIGHT_SMOKE_SPEC
    assert "await page.waitForSelector(`#${view}-view:not(.hidden)`" in _PLAYWRIGHT_SMOKE_SPEC
    assert '<script src="/assets/dashboard_shared.js" defer></script>' in html
    assert '<script src="/assets/dashboard_dialogs.js" defer></script>' in html
    assert '<script src="/assets/dashboard_reports.js" defer></script>' in html
    assert '<script src="/assets/dashboard_strategy_chart.js" defer></script>' in html
    assert '<script src="/assets/dashboard_monitor.js" defer></script>' in html
    assert '<script src="/assets/dashboard.js" defer></script>' in html
    assert html.index("/assets/dashboard_shared.js") < html.index("/assets/dashboard_dialogs.js")
    assert html.index("/assets/dashboard_dialogs.js") < html.index("/assets/dashboard_reports.js")
    assert html.index("/assets/dashboard_reports.js") < html.index("/assets/dashboard_strategy_chart.js")
    assert html.index("/assets/dashboard_strategy_chart.js") < html.index("/assets/dashboard_monitor.js")
    assert html.index("/assets/dashboard_monitor.js") < html.index("/assets/dashboard.js")
    assert "window.HalphaDashboardShared" in script
    assert "window.HalphaDashboardDialogs" in script
    assert "window.HalphaDashboardReports" in script
    assert "window.HalphaDashboardStrategyChart" in script
    assert "window.HalphaDashboardMonitor" in script
    assert 'document.querySelectorAll("[data-view-target]")' in script
    assert "setHashView(node.dataset.viewTarget)" in script
    assert "view is stuck loading" in _PLAYWRIGHT_SMOKE_SPEC
    assert "dashboard-dialog-backdrop" in html
    assert "Generate report dialog did not open" in _PLAYWRIGHT_SMOKE_SPEC
    assert "expect(errors).toEqual([])" in _PLAYWRIGHT_SMOKE_SPEC


@pytest.mark.browser_smoke
@pytest.mark.skipif(
    not BROWSER_SMOKE_ENABLED,
    reason="set HALPHA_BROWSER_SMOKE=1 to run local Playwright dashboard smoke checks",
)
def test_dashboard_primary_pages_browser_smoke(tmp_path: Path) -> None:
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx is None:
        pytest.skip("npx is required for the Playwright browser smoke check.")
    node_modules = _playwright_node_modules(npx)
    if node_modules is None:
        pytest.skip("npx could not expose the @playwright/test package path.")
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    port = _free_port()
    app = create_dashboard_app(config, config_path=config_path, host="127.0.0.1", port=port)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/"
    try:
        _wait_for_dashboard(url)
        spec_path = tmp_path / "dashboard_browser_smoke.spec.js"
        spec_path.write_text(_PLAYWRIGHT_SMOKE_SPEC, encoding="utf-8")
        env = {**os.environ, "HALPHA_DASHBOARD_URL": url}
        existing_node_path = env.get("NODE_PATH")
        env["NODE_PATH"] = str(node_modules) if not existing_node_path else f"{node_modules}{os.pathsep}{existing_node_path}"
        result = subprocess.run(
            [
                npx,
                "--yes",
                "--package",
                "@playwright/test",
                "playwright",
                "test",
                spec_path.name,
                "--browser=chromium",
                "--reporter=line",
                "--workers=1",
            ],
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
            env=env,
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.should_exit = True
        thread.join(timeout=10)


_PLAYWRIGHT_SMOKE_SPEC = textwrap.dedent(
    r"""
    const { test, expect } = require("@playwright/test");
    const views = ["overview", "reports", "strategies", "monitor", "intelligence", "settings"];

    test.use({viewport: {width: 1280, height: 900}});

    test("primary dashboard pages navigate without loading or console failures", async ({ page }) => {
      const url = process.env.HALPHA_DASHBOARD_URL;
      if (!url) throw new Error("HALPHA_DASHBOARD_URL is required");
      const errors = [];
      page.on("console", (message) => {
        if (message.type() === "error") errors.push(`console: ${message.text()}`);
      });
      page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
      await page.goto(url, {waitUntil: "domcontentloaded"});
      await page.waitForSelector('[data-view-target="overview"]', {timeout: 10000});
      const shell = await page.evaluate(() => {
        const sidebar = document.querySelector(".sidebar");
        const main = document.querySelector(".main-shell");
        const bottom = document.querySelector(".sidebar-bottom");
        const sidebarBox = sidebar.getBoundingClientRect();
        const bottomBox = bottom.getBoundingClientRect();
        return {
          bodyOverflowY: getComputedStyle(document.body).overflowY,
          mainOverflowY: getComputedStyle(main).overflowY,
          sidebarHeight: Math.round(sidebarBox.height),
          viewportHeight: window.innerHeight,
          sidebarBottom: Math.round(bottomBox.bottom),
        };
      });
      if (shell.bodyOverflowY !== "hidden") throw new Error("body should not scroll the desktop app shell");
      if (shell.mainOverflowY !== "auto") throw new Error("main shell should own desktop vertical scrolling");
      if (Math.abs(shell.sidebarHeight - shell.viewportHeight) > 1) throw new Error("sidebar height should match the viewport");
      if (shell.sidebarBottom > shell.viewportHeight + 1) throw new Error("sidebar bottom content should stay in the viewport");
      await page.click('[data-report-job="generate"]');
      await page.waitForSelector('#dashboard-dialog-backdrop:not(.hidden)', {timeout: 5000});
      const dialogTitle = await page.locator("#dashboard-dialog-title").innerText();
      if (!dialogTitle.includes("Generate report")) throw new Error("Generate report dialog did not open");
      await page.click("#dashboard-dialog-cancel");
      await page.waitForSelector('#dashboard-dialog-backdrop.hidden', {state: "attached", timeout: 5000});

      for (const view of views) {
        await page.click(`[data-view-target="${view}"]`);
        await page.waitForSelector(`#${view}-view:not(.hidden)`, {timeout: 5000});
        const state = await page.locator(`#${view}-view`).evaluate((node) => {
          const box = node.getBoundingClientRect();
          return {text: node.innerText || "", width: box.width, height: box.height};
        });
        if (!state.text.trim()) throw new Error(`${view} view is blank`);
        if (state.width < 200 || state.height < 120) throw new Error(`${view} view did not render usable dimensions`);
        if (state.text.toLowerCase().includes("loading dashboard")) throw new Error(`${view} view is stuck loading`);
      }

      await page.click('[data-view-target="settings"]');
      await page.click('[data-settings-section="Intelligence sources"]');
      for (const path of ["text.enabled", "macro_calendar.enabled", "onchain_flow.enabled"]) {
        await page.locator(`[data-setting-path="${path}"]`).first().waitFor({state: "visible", timeout: 5000});
      }
      await expect(page.locator('[data-setting-path="text.intelligence.enabled"]')).toHaveCount(0);
      await expect(page.locator('[data-setting-path="macro_calendar.source"]')).toHaveCount(0);
      await expect(page.locator('[data-setting-path="onchain_flow.source"]')).toHaveCount(0);

      await page.click('[data-setting-path="text.enabled"]');
      await page.locator('[data-setting-path="text.intelligence.enabled"]').first().waitFor({state: "visible", timeout: 5000});
      await expect(page.locator('[data-setting-path="text.intelligence.model_cache_dir"]')).toHaveCount(0);
      await page.click('[data-setting-path="text.intelligence.enabled"]');
      for (const path of [
        "text.intelligence.model_cache_dir",
        "text.intelligence.models.embedding.name",
        "text.intelligence.models.classifier.name",
        "text.intelligence.models.sentiment.name",
        "text.intelligence.models.ner.name",
        "text.intelligence.thresholds.duplicate_similarity",
        "text.intelligence.thresholds.max_topic_window_hours",
      ]) {
        await page.locator(`[data-setting-path="${path}"]`).first().waitFor({state: "visible", timeout: 5000});
      }
      await page.click('[data-setting-path="macro_calendar.enabled"]');
      for (const path of [
        "macro_calendar.enabled",
        "macro_calendar.source",
        "macro_calendar.data_classes",
        "macro_calendar.regions",
        "macro_calendar.lookback_days",
        "macro_calendar.lookahead_days",
      ]) {
        await page.locator(`[data-setting-path="${path}"]`).first().waitFor({state: "visible", timeout: 5000});
      }
      await page.click('[data-setting-path="onchain_flow.enabled"]');
      for (const path of [
        "onchain_flow.enabled",
        "onchain_flow.source",
        "onchain_flow.data_classes",
        "onchain_flow.assets",
        "onchain_flow.chains",
        "onchain_flow.lookback_days",
      ]) {
        await page.locator(`[data-setting-path="${path}"]`).first().waitFor({state: "visible", timeout: 5000});
      }
      await expect(page.locator("#change-summary")).toContainText("macro_calendar.enabled");
      await page.click('[data-settings-section="Market data"]');
      await page.locator('[data-setting-path="market.enabled"]').first().waitFor({state: "visible", timeout: 5000});
      await expect(page.locator('[data-setting-path="market.source"]')).toHaveCount(0);
      await expect(page.locator('[data-setting-path="market.derivatives.enabled"]')).toHaveCount(0);
      await page.click('[data-setting-path="market.enabled"]');
      await page.locator('[data-setting-path="market.derivatives.enabled"]').first().waitFor({state: "visible", timeout: 5000});
      await expect(page.locator('[data-setting-path="market.derivatives.source"]')).toHaveCount(0);
      await page.click('[data-setting-path="market.derivatives.enabled"]');
      for (const path of [
        "market.derivatives.enabled",
        "market.derivatives.source",
        "market.derivatives.symbols",
        "market.derivatives.data_classes",
        "market.derivatives.periods",
        "market.derivatives.lookback.8h",
      ]) {
        await page.locator(`[data-setting-path="${path}"]`).first().waitFor({state: "visible", timeout: 5000});
      }
      await page.click('[data-settings-section="Storage"]');
      await page.locator("#cleanup-run-artifacts").waitFor({state: "visible", timeout: 5000});
      await page.locator("#cleanup-shared-data").waitFor({state: "visible", timeout: 5000});

      await page.click('[data-view-target="strategies"]');
      await page.click('[data-strategy-tab="equity"]');
      await page.waitForSelector("#strategy-tab-content", {timeout: 5000});
      await page.click('[data-view-target="intelligence"]');
      await page.click('[data-intel-tab="quality"]');
      await page.waitForSelector("#intel-events", {timeout: 5000});
      await page.setViewportSize({width: 390, height: 820});
      await page.click('[data-view-target="overview"]');
      await page.waitForSelector("#overview-view:not(.hidden)", {timeout: 5000});

      expect(errors).toEqual([]);
    });
    """
).strip()


_PRIMARY_VIEWS = ("overview", "reports", "strategies", "monitor", "intelligence", "settings")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _playwright_node_modules(npx: str) -> Path | None:
    result = subprocess.run(
        [
            npx,
            "--yes",
            "--package",
            "@playwright/test",
            "node",
            "-e",
            "console.log(process.env.PATH)",
        ],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return None
    for part in result.stdout.strip().split(os.pathsep):
        path = Path(part)
        if path.name == ".bin" and path.parent.name == "node_modules" and "_npx" in path.as_posix():
            return path.parent
    return None


def _wait_for_dashboard(url: str) -> None:
    deadline = time.monotonic() + 10
    health_url = f"{url.rstrip('/')}/api/health"
    while time.monotonic() < deadline:
        try:
            with urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("dashboard server did not start before browser smoke timeout")


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
