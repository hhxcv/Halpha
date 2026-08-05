import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "../build/qualification/browser/playwright-results",
  reporter: [["line"], ["json", { outputFile: process.env.HALPHA_PLAYWRIGHT_REPORT ?? "../build/qualification/browser/playwright-report.json" }]],
  retries: 0,
  workers: 1,
  use: {
    baseURL: process.env.HALPHA_BROWSER_BASE_URL ?? "http://127.0.0.1:8765",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "chromium-narrow",
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } },
    },
  ],
});
